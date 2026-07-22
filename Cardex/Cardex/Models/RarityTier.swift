import SwiftUI

enum RarityTier: Int, CaseIterable, Codable {
    case common = 0
    case uncommon = 1
    case rare = 2
    case epic = 3
    case legendary = 4

    var name: String {
        switch self {
        case .common: "Common"
        case .uncommon: "Uncommon"
        case .rare: "Rare"
        case .epic: "Epic"
        case .legendary: "Legendary"
        }
    }

    var color: Color {
        switch self {
        case .common: .cxCommon
        case .uncommon: .cxUncommon
        case .rare: .cxRare
        case .epic: .cxEpic
        case .legendary: .cxLegendary
        }
    }

    var xpReward: Int {
        switch self {
        case .common: 10
        case .uncommon: 25
        case .rare: 50
        case .epic: 100
        case .legendary: 500
        }
    }

    var icon: String {
        switch self {
        case .common: "circle.fill"
        case .uncommon: "diamond.fill"
        case .rare: "star.fill"
        case .epic: "hexagon.fill"
        case .legendary: "crown.fill"
        }
    }
}
