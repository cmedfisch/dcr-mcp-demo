import Foundation

enum AchievementDefinition: String, CaseIterable {
    case firstCatch = "first_catch"
    case tenCatches = "ten_catches"
    case fiftyCatches = "fifty_catches"
    case hundredCatches = "hundred_catches"
    case completeMake = "complete_make"
    case spotLegendary = "spot_legendary"
    case spotAllRarities = "spot_all_rarities"
    case weekStreak = "week_streak"
    case monthStreak = "month_streak"
    case speedDemon = "speed_demon"
    case diverseFleet = "diverse_fleet"
    case vintageFinder = "vintage_finder"
    case electricFuture = "electric_future"

    var title: String {
        switch self {
        case .firstCatch: "First Catch"
        case .tenCatches: "Getting Started"
        case .fiftyCatches: "Serious Spotter"
        case .hundredCatches: "Century Club"
        case .completeMake: "Brand Loyalist"
        case .spotLegendary: "Unicorn Hunter"
        case .spotAllRarities: "Full Spectrum"
        case .weekStreak: "Week Warrior"
        case .monthStreak: "Dedicated"
        case .speedDemon: "Speed Demon"
        case .diverseFleet: "Diverse Fleet"
        case .vintageFinder: "Time Traveler"
        case .electricFuture: "Future Forward"
        }
    }

    var description: String {
        switch self {
        case .firstCatch: "Catch your first car"
        case .tenCatches: "Catch 10 unique cars"
        case .fiftyCatches: "Catch 50 unique cars"
        case .hundredCatches: "Catch 100 unique cars"
        case .completeMake: "Catch every model from one make"
        case .spotLegendary: "Spot a Legendary car"
        case .spotAllRarities: "Catch at least one car from every rarity tier"
        case .weekStreak: "Spot cars 7 days in a row"
        case .monthStreak: "Spot cars 30 days in a row"
        case .speedDemon: "Catch 5 cars in a single day"
        case .diverseFleet: "Catch cars from 10 different makes"
        case .vintageFinder: "Catch a car from before 1970"
        case .electricFuture: "Catch 5 electric vehicles"
        }
    }

    var icon: String {
        switch self {
        case .firstCatch: "camera.fill"
        case .tenCatches: "10.circle.fill"
        case .fiftyCatches: "50.circle.fill"
        case .hundredCatches: "star.circle.fill"
        case .completeMake: "checkmark.seal.fill"
        case .spotLegendary: "crown.fill"
        case .spotAllRarities: "rainbow"
        case .weekStreak: "flame.fill"
        case .monthStreak: "bolt.fill"
        case .speedDemon: "hare.fill"
        case .diverseFleet: "globe"
        case .vintageFinder: "clock.fill"
        case .electricFuture: "bolt.car.fill"
        }
    }
}
