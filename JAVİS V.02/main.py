import asyncio
import os
import socket
import threading
import traceback

from core.live.session import JarvisLive
from ui.desktop import JarvisUI


# =========================================================
# TCP BAGLANTI SISTEMI
# =========================================================
def tcp_sunucuya_baglan(ip: str, port: int) -> None:
    istemci_soketi = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    istemci_soketi.settimeout(10)

    try:
        print(f"[TCP] Sunucuya baglaniliyor -> {ip}:{port}")

        istemci_soketi.connect((ip, port))

        print("[TCP] Baglanti basarili!")

        mesaj = "Jarvis"

        istemci_soketi.sendall(mesaj.encode("utf-8"))

        print(f"[TCP] Gonderilen mesaj -> {mesaj}")

        yanit = istemci_soketi.recv(1024)

        print(f"[TCP] Sunucudan gelen yanit -> {yanit.decode('utf-8')}")

    except socket.timeout:
        print("[TCP] Zaman asimi hatasi!")

    except ConnectionRefusedError:
        print("[TCP] Sunucu baglantiyi reddetti!")

    except Exception as e:
        print(f"[TCP] Baglanti hatasi -> {e}")

    finally:
        istemci_soketi.close()

        print("[TCP] Baglanti kapatildi.")


# =========================================================
# ASYNC JARVIS SISTEMI
# =========================================================
def start_jarvis(ui: JarvisUI) -> None:

    loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)

    try:
        print("[JARVIS] API key kontrol ediliyor...")

        ui.wait_for_api_key()

        print("[JARVIS] API key bulundu.")

        jarvis = JarvisLive(ui)

        print("[JARVIS] Baslatiliyor...")

        loop.run_until_complete(jarvis.run())

    except KeyboardInterrupt:
        print("\n[JARVIS] Kullanici tarafindan kapatildi.")

    except Exception as e:
        hata = str(e)

        print("\n================ HATA =================")
        print(f"[JARVIS] Kritik hata -> {hata}")
        print("=======================================\n")

        # FULL TRACEBACK
        traceback.print_exc()

        # API HATALARI
        if "API key expired" in hata:
            print("[AUTH] API key suresi dolmus!")
            print("[AUTH] Yeni API key olusturulmasi gerekiyor.")

        elif "401" in hata:
            print("[AUTH] Yetkilendirme hatasi!")

        elif "403" in hata:
            print("[AUTH] Erisim engellendi!")

        elif "invalid frame payload data" in hata:
            print("[WEBSOCKET] Sunucu websocket baglantisini kapatti.")

        elif "connection" in hata.lower():
            print("[NETWORK] Baglanti problemi algilandi.")

        elif "timeout" in hata.lower():
            print("[NETWORK] Sunucu zaman asimina ugradi.")

        else:
            print("[SYSTEM] Bilinmeyen hata!")

    finally:
        try:
            pending = asyncio.all_tasks(loop)

            for task in pending:
                task.cancel()

            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )

            loop.run_until_complete(loop.shutdown_asyncgens())

        except Exception as cleanup_error:
            print(f"[CLEANUP] Temizlik hatasi -> {cleanup_error}")

        finally:
            loop.close()

            print("[JARVIS] Event loop kapatildi.")


# =========================================================
# MAIN
# =========================================================
def main() -> None:

    print("===================================")
    print("         JARVIS BASLATILIYOR")
    print("===================================\n")

    # VS CODE KONTROLU
    if os.environ.get("TERM_PROGRAM") == "vscode":
        print("[SYSTEM] VS Code icinden baslatildi.\n")

    # UI
    ui = JarvisUI()

    # TCP SUNUCU BAGLANTISI
    tcp_sunucuya_baglan("127.0.0.1", 8586)

    # JARVIS THREAD
    jarvis_thread = threading.Thread(
        target=start_jarvis,
        args=(ui,),
        daemon=True
    )

    jarvis_thread.start()

    # UI LOOP
    try:
        ui.root.mainloop()

    except KeyboardInterrupt:
        print("\n[UI] Arayuz kapatildi.")

    finally:
        print("[SYSTEM] Program sonlandi.")


# =========================================================
# ENTRY POINT
# =========================================================
if __name__ == "__main__":
    main()