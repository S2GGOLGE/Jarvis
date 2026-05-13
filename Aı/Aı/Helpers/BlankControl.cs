using System;
using Aı.Models.OrientationModels;

namespace Aı.Helpers.BoşKontrol
{
    public class BlankControl
    {
        public bool Kontrol(Orientation orientation)
        {
            if (orientation == null || string.IsNullOrEmpty(orientation.Konu))
            {
                Console.WriteLine("Mesaj gir Patron");
                return false;
            }

            return true;
        }
    }
}