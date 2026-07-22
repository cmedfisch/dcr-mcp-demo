import Foundation
import SwiftData

@Model
final class Car {
    @Attribute(.unique) var catalogID: String
    var make: String = ""
    var model: String = ""
    var generation: String = ""
    var yearStart: Int = 0
    var yearEnd: Int = 0

    var bodyType: String = ""
    var engineType: String = ""
    var displacement: String = ""
    var horsepower: Int?

    var productionCount: Int?
    var rarityTier: Int = 0
    var rarityScore: Double = 0.0

    @Relationship(deleteRule: .cascade, inverse: \Spot.car)
    var spots: [Spot] = []

    var isCaught: Bool { !spots.isEmpty }

    var displayYear: String {
        if yearEnd == 0 || yearEnd >= 2026 {
            return "\(yearStart)–present"
        }
        return yearStart == yearEnd ? "\(yearStart)" : "\(yearStart)–\(yearEnd)"
    }

    var rarity: RarityTier {
        RarityTier(rawValue: rarityTier) ?? .common
    }

    var xpValue: Int {
        rarity.xpReward
    }

    init(catalogID: String, make: String, model: String, generation: String,
         yearStart: Int, yearEnd: Int, bodyType: String, engineType: String,
         displacement: String, horsepower: Int? = nil, productionCount: Int? = nil) {
        self.catalogID = catalogID
        self.make = make
        self.model = model
        self.generation = generation
        self.yearStart = yearStart
        self.yearEnd = yearEnd
        self.bodyType = bodyType
        self.engineType = engineType
        self.displacement = displacement
        self.horsepower = horsepower
        self.productionCount = productionCount
    }
}
