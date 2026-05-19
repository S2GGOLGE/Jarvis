import asyncio
import os
import socket
import threading
from ui.ui import JarvisUI
from core.live.jarvislive import JarvisLive  # ← düzeltildi

def main():
    if os.environ.get("TERM_PROGRAM") == "vscode":
        print("[JARVIS] VS Code icinden baslatildi.")

    ui = JarvisUI()

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Kapatılıyor...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()


def tcp_sunucuya_baglan(ip: str, port: int) -> None:
    istemci_soketi = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"Sunucuya bağlanılıyor: {ip}:{port}")
        istemci_soketi.connect((ip, port))
        print("Bağlantı başarılı!")

        mesaj = "Jarvis"
        istemci_soketi.sendall(mesaj.encode("utf-8"))
        print(f"Gönderilen mesaj: {mesaj}")

        yanit = istemci_soketi.recv(1024)
        print(f"Sunucudan gelen yanıt: {yanit.decode('utf-8')}")

    except Exception as e:
        print(f"Bağlantı hatası: {e}")

    finally:
        istemci_soketi.close()
        print("Bağlantı kapatıldı.")


if __name__ == "__main__":
    tcp_sunucuya_baglan("127.0.0.1", 8586)
    main()