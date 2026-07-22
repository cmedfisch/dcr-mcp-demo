import Foundation
import SwiftData

enum PreviewSampleData {
    static let sampleCars: [Car] = [
        Car(catalogID: "Ferrari|F40|1987-1992", make: "Ferrari", model: "F40",
            generation: "", yearStart: 1987, yearEnd: 1992,
            bodyType: "coupe", engineType: "gasoline", displacement: "2.9L V8",
            horsepower: 471, productionCount: 1315),
        Car(catalogID: "Toyota|Supra|2019-0", make: "Toyota", model: "Supra",
            generation: "A90", yearStart: 2019, yearEnd: 0,
            bodyType: "coupe", engineType: "gasoline", displacement: "3.0L I6",
            horsepower: 382),
        Car(catalogID: "Koenigsegg|Agera RS|2015-2018", make: "Koenigsegg", model: "Agera RS",
            generation: "", yearStart: 2015, yearEnd: 2018,
            bodyType: "coupe", engineType: "gasoline", displacement: "5.0L V8",
            horsepower: 1160, productionCount: 25),
    ]

    @MainActor
    static var container: ModelContainer {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try! ModelContainer(for: Car.self, Spot.self, Player.self, Achievement.self,
                                            configurations: config)
        let context = container.mainContext

        for car in sampleCars {
            let rarity = RarityCalculator.calculateTier(
                productionCount: car.productionCount,
                yearStart: car.yearStart,
                yearEnd: car.yearEnd,
                bodyType: car.bodyType,
                make: car.make
            )
            car.rarityTier = rarity.tier.rawValue
            car.rarityScore = rarity.score
            context.insert(car)
        }

        let player = Player()
        player.totalXP = 350
        player.currentStreak = 3
        player.longestStreak = 7
        context.insert(player)

        try? context.save()
        return container
    }
}
