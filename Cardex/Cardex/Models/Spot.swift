import Foundation
import SwiftData

@Model
final class Spot {
    var car: Car?
    var photoFileName: String = ""
    var dateCaught: Date = Date()
    var latitude: Double?
    var longitude: Double?
    var locationName: String = ""
    var notes: String = ""
    var isFavorite: Bool = false

    init(car: Car?, photoFileName: String, dateCaught: Date = .now,
         latitude: Double? = nil, longitude: Double? = nil,
         locationName: String = "", notes: String = "") {
        self.car = car
        self.photoFileName = photoFileName
        self.dateCaught = dateCaught
        self.latitude = latitude
        self.longitude = longitude
        self.locationName = locationName
        self.notes = notes
    }
}
