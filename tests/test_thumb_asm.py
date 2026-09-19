"""Tests for the minimal Thumb-2 assembler in ``gnwmanager.cli.gnw_patch.thumb_asm``.

The assembler is validated against keystone-engine (a dev dependency) as the
reference: the tests exhaustively compare our encoder to keystone across the full
valid operand range, plus the exact instruction strings the Mario/Zelda patches
emit. A small number of unit checks need no keystone at all.
"""

import pytest

from gnwmanager.cli.gnw_patch.thumb_asm import (
    ThumbAssemblyError,
    assemble,
    encode_modified_immediate,
    iter_modified_immediates,
)

# keystone has no macOS-arm64 wheel; skip the reference-comparison suite there
# rather than building it from sdist. It is installed on the other CI platforms.
ks = pytest.importorskip("keystone")


@pytest.fixture(scope="module")
def keystone():
    return ks.Ks(ks.KS_ARCH_ARM, ks.KS_MODE_THUMB)


def ks_asm(keystone, code, addr=0):
    """Assemble with keystone, returning bytes or ``None`` if it rejects the input."""
    try:
        encoding, _ = keystone.asm(code, addr)
    except ks.KsError:
        return None
    return encoding


def assert_match(keystone, code, addr=0):
    expected = ks_asm(keystone, code, addr)
    if expected is None:
        with pytest.raises(ThumbAssemblyError):
            assemble(code, addr)
    else:
        assert assemble(code, addr) == expected, code


# --------------------------------------------------------------------------- #
# keystone-backed exhaustive / range comparisons
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rd", ["r0", "r2", "r3", "r7", "r12"])
def test_movw_full_range(keystone, rd):
    for imm in range(0, 0x10000):
        code = f"movw {rd}, #{imm}"
        assert assemble(code) == keystone.asm(code)[0], code


def test_encode_modified_immediate_round_trips(keystone):
    # Every representable modified immediate must encode identically to keystone.
    for value in iter_modified_immediates():
        code = f"mov.w r4, #{value}"
        assert assemble(code) == keystone.asm(code)[0], hex(value)


def test_mov_w_rejects_unrepresentable(keystone):
    # Values keystone refuses (not a modified immediate) we must refuse too.
    unrepresentable = [7000, 0x1B58, 0x12345, 0x101, 0xABCD, 0x80000001]
    for value in unrepresentable:
        code = f"mov.w r2, #{value}"
        assert ks_asm(keystone, code) is None, f"keystone unexpectedly accepted {code}"
        with pytest.raises(ThumbAssemblyError):
            assemble(code)


@pytest.mark.parametrize("cond", ["eq", "ne", "cs", "mi", "ge", "le"])
def test_conditional_mov_w(keystone, cond):
    # Conditional ``mov.w`` is only legal inside an IT block (keystone rejects it
    # standalone), so assemble it the way the patcher actually emits it.
    for value in [0, 0x1000, 0x30000, 0x87000, 0xFF000, 45056]:
        code = f"it {cond}; mov{cond}.w r4, #{value}"
        assert_match(keystone, code)


@pytest.mark.parametrize("mnemonic", ["add.w", "sub.w"])
@pytest.mark.parametrize("rn", ["r0", "r1", "r2", "r8"])
def test_add_sub_w(keystone, mnemonic, rn):
    for value in [0, 0x10, 0xFF, 0x100, 0x1000, 45056, 0xFF000]:
        code = f"{mnemonic} r3, {rn}, #{value}"
        assert_match(keystone, code)


@pytest.mark.parametrize("rt", ["r0", "r4", "r12", "sp", "lr", "pc"])
def test_ldr_w_pc_literal(keystone, rt):
    for imm in [0, 4, 0x84, 100, 0xFFF, -4, -460, -568, -0xFFF]:
        code = f"ldr.w {rt}, [pc, #{imm}]"
        assert_match(keystone, code)


@pytest.mark.parametrize("mnemonic", ["add", "sub"])
@pytest.mark.parametrize("cond", ["eq", "ne", "cs", "mi", "ge", "le"])
def test_conditional_add_sub_w(keystone, mnemonic, cond):
    # Conditional add.w/sub.w are only legal inside an IT block.
    for value in [0, 0x10, 0xFF, 0x1000, 0xFF000]:
        code = f"it {cond}; {mnemonic}{cond}.w r4, r4, #{value}"
        assert_match(keystone, code)


@pytest.mark.parametrize(
    "code,addr",
    [
        # The exact relocated-NVRAM sequences emitted by mario.py in PR #381,
        # using the real (negative) PC-relative literal offsets.
        (f"ldr.w r4, [pc, #{0x468C - ((0x4856 + 4) & ~3)}]; it ne; addne.w r4, r4, #0x1000", 0x4856),
        (f"ldr.w r4, [pc, #{0x468C - ((0x48C0 + 4) & ~3)}]; it ne; addne.w r4, r4, #0x1000", 0x48C0),
    ],
)
def test_pr381_nvram_sequences(keystone, code, addr):
    assert_match(keystone, code, addr)


def test_mov_register_all_pairs(keystone):
    regs = [f"r{i}" for i in range(13)] + ["sp", "lr", "pc"]
    for rd in regs:
        for rm in regs:
            code = f"mov {rd}, {rm}"
            assert_match(keystone, code)


def test_sub_sp(keystone):
    for imm in range(0, 0x200, 4):
        code = f"sub sp, #{imm}"
        assert_match(keystone, code)


def test_b_narrow_range(keystone):
    # Narrow B is PC-relative; sweep aligned targets around the encodable window.
    addr = 0x1000
    for target in range(addr - 0x420, addr + 0x420, 2):
        if target < 0:
            continue
        code = f"b #{target}"
        assert_match(keystone, code, addr)


def test_b_wide_range(keystone):
    addr = 0x0800_0000
    for delta in range(-0x2000, 0x2000, 2):
        target = addr + delta
        code = f"b.w #{target}"
        assert_match(keystone, code, addr)


def test_b_wide_large_offsets(keystone):
    addr = 0x0800_0000
    for delta in [-0x80_0000, -0x10_0000, 0x10_0000, 0x7F_FFFE]:
        code = f"b.w #{addr + delta}"
        assert_match(keystone, code, addr)


@pytest.mark.parametrize(
    "mnemonic",
    ["it", "itt", "ite", "ittt", "itte", "itet", "itee", "itete"],
)
@pytest.mark.parametrize("cond", ["eq", "ne", "cs", "mi", "ge", "lt", "gt", "le"])
def test_it_blocks(keystone, mnemonic, cond):
    code = f"{mnemonic} {cond}"
    assert_match(keystone, code)


def test_multi_instruction_sequence(keystone):
    code = "ite ne; movne.w r4, #0x1000; moveq.w r4, #0x0"
    assert assemble(code) == keystone.asm(code)[0]


# The exact instruction strings the Mario/Zelda patches emit, including their
# irregular whitespace, so the parser is exercised on real-world formatting (the
# range tests above use tidy f-string output). Dynamic immediates use a
# representative value.
PATCHER_INSTRUCTIONS = [
    ("mov.w r1, #0x00000", 0),
    ("movw r2, #1500", 0),  # movw r2, #{sleep_time_frames}
    ("b 0x1c", 0),
    ("mov.w r2, #45056", 0),  # mov.w r2, #{compressed_len}
    ("mov.w r3, #45056", 0),
    ("add.w r2,r1,#0x10", 0),
    ("add.w r7,r0,#0x10", 0),
    ("sub.w r1,r8,#0x10", 0),
    ("sub.w r6,r2,#0x10", 0),
    ("mov r1,r2", 0),
    ("mov   r5,r1", 0),
    ("sub   sp,#0x10", 0),
    ("mov   r1,r6", 0),
    ("mov   r0,r7", 0),
    ("mov   r2,r7", 0),
    ("mov   r0,r5", 0),
    ("mov r7,r0", 0),
    ("ite ne; movne.w r4, #0xff000; moveq.w r4, #0xfe000", 0),
    ("b.w #0x8018224", 0x800F430),
    ("b.w #0x801b504", 0x800F430),
    ("b.w #0x801b5b4", 0x800F430),
    ("b.w #0x801b5b8", 0x800F430),
    ("b.w #0x801b5e4", 0x800F430),
    ("b.w #0x801b5e8", 0x800F430),
]


@pytest.mark.parametrize("code,addr", PATCHER_INSTRUCTIONS, ids=[c for c, _ in PATCHER_INSTRUCTIONS])
def test_patcher_instruction_strings(keystone, code, addr):
    assert_match(keystone, code, addr)


@pytest.mark.parametrize(
    "code",
    [
        "movw sp, #1",
        "movw pc, #1",
        "mov.w sp, #1",
        "mov.w pc, #1",
        "add.w pc, r0, #1",
        "add.w r0, pc, #1",
        "sub.w pc, r0, #1",
        "sub.w r0, pc, #1",
    ],
)
def test_rejects_disallowed_registers(keystone, code):
    # These register operands are rejected by keystone (UNPREDICTABLE / different
    # encoding); assert_match confirms we reject them too.
    assert ks_asm(keystone, code) is None, f"keystone unexpectedly accepted {code}"
    assert_match(keystone, code)


# --------------------------------------------------------------------------- #
# unit checks that do not require keystone
# --------------------------------------------------------------------------- #
def test_encode_modified_immediate_examples():
    assert encode_modified_immediate(0) == 0x000
    assert encode_modified_immediate(0xFF) == 0x0FF
    assert encode_modified_immediate(0x00FF00FF) == 0x1FF
    assert encode_modified_immediate(0xFF00FF00) == 0x2FF
    assert encode_modified_immediate(0xFFFFFFFF) == 0x3FF
    assert encode_modified_immediate(0xB000) == 0xC30  # 45056, rotation form


def test_encode_modified_immediate_rejects():
    with pytest.raises(ThumbAssemblyError):
        encode_modified_immediate(0x101)


def test_unsupported_instruction():
    with pytest.raises(ThumbAssemblyError):
        assemble("push {r0}")
