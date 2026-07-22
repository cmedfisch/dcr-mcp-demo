import Foundation
import SwiftData

@Model
final class Achievement {
    var player: Player?
    var definitionID: String = ""
    var dateEarned: Date = Date()

    init(player: Player?, definitionID: String) {
        self.player = player
        self.definitionID = definitionID
        self.dateEarned = .now
    }
}
