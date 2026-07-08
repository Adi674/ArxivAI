# scripts/local_db_proxy.py
import socket
import threading
import sys

LOCAL_PORT = 5435
REMOTE_HOST = "db.fplmgibqyrzrqtxslceg.supabase.co"
REMOTE_PORT = 5432

def handle_client(client_socket):
    try:
        remote_socket = socket.create_connection((REMOTE_HOST, REMOTE_PORT), timeout=10)
    except Exception as e:
        client_socket.close()
        return

    def forward(source, destination):
        try:
            while True:
                data = source.recv(4096)
                if not data:
                    break
                destination.sendall(data)
        except Exception:
            pass
        finally:
            source.close()
            destination.close()

    threading.Thread(target=forward, args=(client_socket, remote_socket), daemon=True).start()
    threading.Thread(target=forward, args=(remote_socket, client_socket), daemon=True).start()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(('0.0.0.0', LOCAL_PORT))
        server.listen(100)
        print(f"Local DB Proxy listening on 0.0.0.0:{LOCAL_PORT} -> {REMOTE_HOST}:{REMOTE_PORT}", flush=True)
    except Exception as e:
        print(f"Failed to bind local port: {e}", flush=True)
        sys.exit(1)

    try:
        while True:
            client_sock, addr = server.accept()
            handle_client(client_sock)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()

if __name__ == "__main__":
    main()
