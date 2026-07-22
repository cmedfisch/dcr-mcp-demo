import Foundation

enum RarityCalculator {
    static func calculateTier(
        productionCount: Int?,
        yearStart: Int,
        yearEnd: Int,
        bodyType: String,
        make: String
    ) -> (tier: RarityTier, score: Double) {
        let volume: Double
        if let known = productionCount {
            volume = Double(known)
        } else {
            let currentYear = 2026
            let endYear = yearEnd == 0 ? currentYear : yearEnd
            let years = max(1, endYear - yearStart)
            let segment = segmentMultiplier(for: bodyType)
            let brand = brandTier(for: make)
            volume = Double(years) * segment * brand
        }

        let tier = tierFromVolume(volume)
        let score = normalizedScore(volume: volume, tier: tier)
        return (tier, score)
    }

    private static func tierFromVolume(_ volume: Double) -> RarityTier {
        switch volume {
        case 5_000_001...: return .common
        case 1_000_001...5_000_000: return .uncommon
        case 100_001...1_000_000: return .rare
        case 10_001...100_000: return .epic
        default: return .legendary
        }
    }

    private static func normalizedScore(volume: Double, tier: RarityTier) -> Double {
        let (low, high): (Double, Double) = switch tier {
        case .common: (5_000_001, 50_000_000)
        case .uncommon: (1_000_001, 5_000_000)
        case .rare: (100_001, 1_000_000)
        case .epic: (10_001, 100_000)
        case .legendary: (1, 10_000)
        }
        let clamped = min(max(volume, low), high)
        return 1.0 - ((clamped - low) / (high - low))
    }

    private static func segmentMultiplier(for bodyType: String) -> Double {
        let type = bodyType.lowercased()
        if type.contains("sedan") { return 500_000 }
        if type.contains("suv") || type.contains("crossover") { return 400_000 }
        if type.contains("truck") || type.contains("pickup") { return 350_000 }
        if type.contains("hatchback") || type.contains("compact") { return 300_000 }
        if type.contains("wagon") || type.contains("estate") { return 150_000 }
        if type.contains("van") || type.contains("minivan") { return 200_000 }
        if type.contains("coupe") { return 150_000 }
        if type.contains("convertible") || type.contains("roadster") || type.contains("cabriolet") { return 80_000 }
        if type.contains("sports") || type.contains("sport") { return 50_000 }
        if type.contains("super") || type.contains("hyper") { return 5_000 }
        return 200_000
    }

    private static func brandTier(for make: String) -> Double {
        let m = make.lowercased()
        let massMarket = ["toyota", "honda", "ford", "chevrolet", "chevy", "volkswagen", "vw",
                          "hyundai", "kia", "nissan", "mazda", "subaru", "mitsubishi", "suzuki",
                          "fiat", "renault", "peugeot", "citroen", "skoda", "seat", "dacia",
                          "chrysler", "dodge", "jeep", "ram", "gmc", "buick"]
        let premium = ["bmw", "mercedes", "mercedes-benz", "audi", "lexus", "infiniti",
                       "acura", "volvo", "cadillac", "lincoln", "genesis", "alfa romeo"]
        let luxury = ["porsche", "maserati", "jaguar", "land rover", "bentley", "rolls-royce",
                      "aston martin", "lotus", "mclaren"]
        let exotic = ["ferrari", "lamborghini", "pagani", "koenigsegg", "bugatti",
                      "rimac", "gordon murray", "hennessey", "ssc"]

        if exotic.contains(m) { return 0.02 }
        if luxury.contains(m) { return 0.15 }
        if premium.contains(m) { return 0.4 }
        if massMarket.contains(m) { return 1.0 }
        return 0.3
    }
}
