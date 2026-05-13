using System;
using Aı.Models.OrientationModels;
using Aı.Helpers.BoşKontrol;

namespace Aı.Controllers
{
    internal class OrientationControllers
    {
        private readonly BlankControl _bosKontrol = new BlankControl();

        public void Yonlendirme(Orientation orientation)
        {
            // boş kontrol
            if (!_bosKontrol.Kontrol(orientation))
                return;

            // işlem
            Console.WriteLine("Konu: " + orientation.Konu);
        }
    }
}