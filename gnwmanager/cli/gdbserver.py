from time import sleep

from pyocd.gdbserver import GDBServer


def gdbserver():
    from .main import session

    gdb = GDBServer(session, core=0)
    # session.subscribe(_gdbserver_listening_cb, GDBServer.GDBSERVER_START_LISTENING_EVENT, gdb)
    session.gdbservers[0] = gdb
    gdb.start()

    while gdb.is_alive():
        sleep(0.1)
