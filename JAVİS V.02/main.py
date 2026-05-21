import asyncio
import os
import socket
import threading

from core.live.session import JarvisLive
from ui.desktop import JarvisUI


def main():
    if os.environ.get("TERM_PROGRAM") == "vscode":
        print("[JARVIS] VS Code icinden baslatildi.")

    ui = JarvisUI()

    def runner():
        ui.wait_for_api_key()

        jarvis = JarvisLive(ui)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(jarvis.run())

        except KeyboardInterrupt:
            print("\n[JARVIS] Kapatiliyor...")

        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    threading.Thread(target=runner, daemon=True).start()

    ui.root.mainloop()


def tcp_sunucuya_baglan(ip: str, port: int) -> None:
    istemci_soketi = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        print(f"Sunucuya baglaniliyor: {ip}:{port}")
        istemci_soketi.connect((ip, port))
        print("Baglanti basarili!")

        mesaj = "Jarvis"
        istemci_soketi.sendall(mesaj.encode("utf-8"))
        print(f"Gonderilen mesaj: {mesaj}")

        yanit = istemci_soketi.recv(1024)
        print(f"Sunucudan gelen yanit: {yanit.decode('utf-8')}")

    except Exception as e:
        print(f"Baglanti hatasi: {e}")

    finally:
        istemci_soketi.close()
        print("Baglanti kapatildi.")


if __name__ == "__main__":
    tcp_sunucuya_baglan("127.0.0.1", 8586)
    main()
