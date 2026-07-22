import Foundation
import SwiftData

enum CarCatalogService {
    @MainActor
    static func seed(context: ModelContext) async {
        guard let url = Bundle.main.url(forResource: "car_catalog", withExtension: "json") else { return }
        guard let data = try? Data(contentsOf: url) else { return }
        guard let entries = try? JSONDecoder().decode([CatalogEntry].self, from: data) else { return }

        for batch in entries.chunked(into: 500) {
            for entry in batch {
                let car = Car(
                    catalogID: "\(entry.make)|\(entry.model)|\(entry.yearStart)-\(entry.yearEnd)",
                    make: entry.make,
                    model: entry.model,
                    generation: entry.generation ?? "",
                    yearStart: entry.yearStart,
                    yearEnd: entry.yearEnd,
                    bodyType: entry.bodyType ?? "",
                    engineType: entry.engineType ?? "",
                    displacement: entry.displacement ?? "",
                    horsepower: entry.horsepower,
                    productionCount: entry.productionCount
                )
                let rarity = RarityCalculator.calculateTier(
                    productionCount: entry.productionCount,
                    yearStart: entry.yearStart,
                    yearEnd: entry.yearEnd,
                    bodyType: entry.bodyType ?? "",
                    make: entry.make
                )
                car.rarityTier = rarity.tier.rawValue
                car.rarityScore = rarity.score
                context.insert(car)
            }
            try? context.save()
        }
    }
}

struct CatalogEntry: Codable {
    let make: String
    let model: String
    let generation: String?
    let yearStart: Int
    let yearEnd: Int
    let bodyType: String?
    let engineType: String?
    let displacement: String?
    let horsepower: Int?
    let productionCount: Int?
}

extension Array {
    func chunked(into size: Int) -> [[Element]] {
        stride(from: 0, to: count, by: size).map {
            Array(self[$0..<Swift.min($0 + size, count)])
        }
    }
}
