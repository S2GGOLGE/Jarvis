using System;
using System.Net.Sockets;
using System.Text;

namespace Aı.Clinent
{
    public class Clinent
    {
        private TcpClient _client = new TcpClient();

        public void Connect(string host, int port)
        {
            try
            {
                Console.WriteLine("SUNUCUYA BAĞLANIYOR...");

                _client.BeginConnect(host, port, ConnectCallback, null);
            }
            catch (Exception ex)
            {
                Console.WriteLine("Bağlantı hatası: " + ex.Message);
            }
        }

        private void ConnectCallback(IAsyncResult ar)
        {
            try
            {
                _client.EndConnect(ar);

                if (_client.Connected)
                {
                    Console.WriteLine("SUNUCUYA BAŞARIYLA BAĞLANDI");

                    // 🔥 KENDİNİ TANIT
                    Send("JARVİS BAĞLANDI | VERSİYON: 1.0");
                }
                else
                {
                    Console.WriteLine("BAĞLANTI BAŞARISIZ");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("Callback hata: " + ex.Message);
            }
        }

        private void Send(string message)
        {
            try
            {
                NetworkStream stream = _client.GetStream();
                byte[] data = Encoding.UTF8.GetBytes(message);

                stream.Write(data, 0, data.Length);

                Console.WriteLine("TANITIM GÖNDERİLDİ");
            }
            catch (Exception ex)
            {
                Console.WriteLine("Send hata: " + ex.Message);
            }
        }
    }
}