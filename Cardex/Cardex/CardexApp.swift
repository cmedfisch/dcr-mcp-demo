import SwiftUI
import SwiftData

@main
struct CardexApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
        }
        .modelContainer(for: [
            Car.self,
            Spot.self,
            Player.self,
            Achievement.self,
        ])
    }
}
