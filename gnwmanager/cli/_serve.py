import asyncio
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any, Callable, Optional

from cyclopts import Parameter

from gnwmanager.cli.main import app
from gnwmanager.ocdbackend import OCDBackend


@app.command(group="Developer")
def serve(
    port: int = 8765,
    *,
    bind: str = "127.0.0.1",
    cert: Optional[Path] = None,
    key: Optional[Path] = None,
    origin: Optional[list[str]] = None,
    backend_factory: Annotated[Callable[[], dict[str, Any]], Parameter(parse=False)],
):
    """Serve the selected debug backend to a remote browser over WebSocket.

    Parameters
    ----------
    port
        WebSocket port, separate from the GDB backend's TCP port.
    bind
        Listening address. Loopback by default; use an SSH tunnel for remote hosts.
    cert
        TLS certificate for secure WebSockets.
    key
        TLS private key, supplied together with cert.
    origin
        Allowed browser origins. Repeat the option to allow multiple sites.
    """
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    if bool(cert) != bool(key):
        raise ValueError("Supply both --cert and --key")
    try:
        from gnwmanager.server import serve_backend
    except ImportError as error:
        raise RuntimeError('Install WebSocket support with pip install "gnwmanager[serve]"') from error
    options = backend_factory()
    print(f"Serving {options['backend_name']} at {'wss' if cert else 'ws'}://{bind}:{port}/gdb")
    with suppress(KeyboardInterrupt):
        asyncio.run(serve_backend(**options, bind=bind, port=port, cert=cert, key=key, origins=origin))
