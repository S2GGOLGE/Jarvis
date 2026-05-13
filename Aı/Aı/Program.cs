using System;
using Aı.Controllers;
using Aı.Models.OrientationModels;
using Aı.Clinent;

class Program
{
    static void Main()
    {
        // 🔌 HOME / SERVER BAĞLANTISI
        Clinent client = new Clinent();
        client.Connect("127.0.0.1", 8586);

        OrientationControllers controller = new OrientationControllers();
        Orientation model;

        while (true)
        {
            Console.Write("Konu gir (çıkış: exit): ");
            string input = Console.ReadLine();

            if (string.Equals(input, "exit", StringComparison.OrdinalIgnoreCase))
                break;

            model = new Orientation
            {
                Konu = input
            };

            controller.Yonlendirme(model);

            Console.WriteLine();
        }

        Console.WriteLine("Program kapandı. Bir tuşa basın...");
        Console.ReadKey();
    }
}