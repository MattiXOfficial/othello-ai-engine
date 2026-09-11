"""Discovery Service Module (UDP Broadcast)."""

import json
import socket
import threading
import time

from othello.common.i18n_manager import I18nManager


def _(message):
    return I18nManager().gettext(message)


class DiscoveryService:
    """Handles UDP broadcasting to announce server presence."""

    BROADCAST_PORT = 12346
    CLEAR_TIMEOUT = 30  # seconds

    def __init__(self, server_name: str, tcp_port: int = 12345):
        self.server_name = server_name
        self.tcp_port = tcp_port

        self.is_broadcasting = False
        self.is_listening = False

        self.broadcast_thread = None
        self.listen_thread = None
        self.clear_thread = None

        self.discovered_servers = {}
        self.lock = threading.Lock()

    def start_broadcasting(self):
        """Starts the background thread to broadcast presence periodically."""
        if self.is_broadcasting:
            return
        self.is_broadcasting = True
        self.broadcast_thread = threading.Thread(
            target=self.broadcast_presence, daemon=True
        )
        self.broadcast_thread.start()

    def stop_broadcasting(self):
        """Stops the broadcast thread and sends a shutdown message."""
        self.is_broadcasting = False
        self.broadcast_shutdown()

    def start_listening(self):
        """Starts background threads to listen for servers.

        Also clears inactive ones.
        """
        if self.is_listening:
            return
        self.is_listening = True
        self.listen_thread = threading.Thread(
            target=self.listen_for_servers, daemon=True
        )
        self.listen_thread.start()

        self.clear_thread = threading.Thread(
            target=self.clear_inactive_servers, daemon=True
        )
        self.clear_thread.start()

    def stop_listening(self):
        """Stops listening for other servers."""
        self.is_listening = False

    def broadcast_presence(self):
        """Loop to broadcast presence every 10 seconds."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        message = json.dumps(
            {
                "type": "PRESENCE",
                "name": self.server_name,
                "port": self.tcp_port,
            }
        ).encode("utf-8")

        while self.is_broadcasting:
            try:
                sock.sendto(message, ("<broadcast>", self.BROADCAST_PORT))
            except Exception:
                pass
            time.sleep(10)
        sock.close()

    def broadcast_shutdown(self):
        """Broadcast a shutdown message to notify others of offline status."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        message = json.dumps(
            {
                "type": "SHUTDOWN",
                "name": self.server_name,
                "port": self.tcp_port,
            }
        ).encode("utf-8")

        try:
            sock.sendto(message, ("<broadcast>", self.BROADCAST_PORT))
        except OSError:
            pass
        sock.close()

    def listen_for_servers(self):
        """Loop to listen for broadcast presences on UDP port 12345."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.BROADCAST_PORT))
            sock.settimeout(1.0)
        except Exception as e:
            print(_("Error binding UDP listener: {error}").format(error=e))
            return

        while self.is_listening:
            try:
                data, addr = sock.recvfrom(1024)
                ip = addr[0]
                msg = json.loads(data.decode("utf-8"))

                if msg.get("type") == "PRESENCE":
                    self.update_local_list(
                        msg.get("name"), ip, msg.get("port")
                    )
                elif msg.get("type") == "SHUTDOWN":
                    self.remove_from_local_list(
                        msg.get("name"), ip, msg.get("port")
                    )
            except (socket.timeout, json.JSONDecodeError):
                continue
            except Exception as e:
                if self.is_listening:
                    print(
                        _("Discovery listener error: {error}").format(error=e)
                    )
                break
        sock.close()

    def update_local_list(self, name: str, ip: str, port: int):
        """Registers or updates a server timestamp."""
        if not name or not port:
            return
        key = f"{name}@{ip}:{port}"
        with self.lock:
            self.discovered_servers[key] = time.time()

    def remove_from_local_list(self, name: str, ip: str, port: int):
        """Removes a server from the discovered list explicitly."""
        key = f"{name}@{ip}:{port}"
        with self.lock:
            if key in self.discovered_servers:
                del self.discovered_servers[key]

    def clear_inactive_servers(self):
        """Loop to clear servers not seen for CLEAR_TIMEOUT seconds."""
        while self.is_listening:
            time.sleep(5)
            now = time.time()
            with self.lock:
                to_remove = []
                for key, last_seen in self.discovered_servers.items():
                    if now - last_seen > self.CLEAR_TIMEOUT:
                        to_remove.append(key)
                for key in to_remove:
                    del self.discovered_servers[key]

    def get_server_list(self) -> list[str]:
        """Returns the list of currently valid discovered server strings."""
        with self.lock:
            return list(self.discovered_servers.keys())
