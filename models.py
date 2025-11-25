class Event:
    def __init__(self, id, title, date, category, site, image, city, banner, tickets, time, price, map):
        self.id = id
        self.title = title
        self.category = category
        self.date = date
        self.site = site
        self.image = image
        self.city = city
        self.banner = banner
        self.tickets = tickets
        self.time = time
        self.price = price
        self.map = map

events = [
    Event(1, "DTMF Tour", "26 Ene Lun 2026", "Concierto", "Estadio Atanasio Girardot", "dtmftour.png", "Medellin, Antioquia", "dtmfbanner.png", "1200", "16:00 hrs", "230000", "https://www.google.com/maps?q=Estadio+Atanasio+Girardot,+Medellin,+Antioquia&output=embed"),
    Event(2, "El Ultimo Baile", "01 Jun Dom 2026", "Concierto", "Parque de la Leyenda", "elultimobaile.png", "Valledupar, Cesar", "elultimobailebanner.png", "1800", "16:00 hrs", "56000", "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d21814.406114622572!2d-73.27918446927484!3d10.496779115533847!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x8e8ab83b7540bedf%3A0x3f6957c2b897c4d8!2sParque%20de%20la%20Leyenda!5e0!3m2!1ses-419!2sco!4v1748489504226!5m2!1ses-419!2sco"),
]