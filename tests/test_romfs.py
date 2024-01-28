from gnwmanager.romfs import Entry, Header, RomFS, subset_sum


def test_empty_fs():
    romfs = RomFS(Header(0, 0, 1 << 20), [])
    # TODO


def test_fs_add():
    pass


def test_subset_sum_performance(benchmark):
    # Sample data for testing
    numbers = (12, 1, 61, 5, 7, 2)
    target = 24
    limit = 3

    result = benchmark(subset_sum, numbers, target, limit)

    # Verify if the result is correct
    assert sum(numbers[i] for i in result) == target
