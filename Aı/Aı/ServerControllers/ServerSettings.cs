 namespace Aı.ServerSettings
{
    public class ServerSettings
    {
        /*Bu sınıf, yapay zekanın sunucu ayarlarını yönetir.*/
        public static string HOST { get; private set; }
        public static int PORT { get; private set; }
        public static void serverayar(string host, int port)
        {
            HOST = host;
            PORT = port;
        }
    }

}