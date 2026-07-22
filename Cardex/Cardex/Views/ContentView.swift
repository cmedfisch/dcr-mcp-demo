import SwiftUI
import SwiftData

struct ContentView: View {
    @Environment(\.modelContext) private var modelContext
    @Query private var players: [Player]
    @State private var selectedTab = 0
    @State private var isSeeding = false

    var body: some View {
        ZStack {
            if isSeeding {
                SeedingView()
            } else {
                TabView(selection: $selectedTab) {
                    CardexView()
                        .tabItem {
                            Label("Cardex", systemImage: "square.grid.3x3.fill")
                        }
                        .tag(0)

                    SpotFlowView()
                        .tabItem {
                            Label("Spot", systemImage: "camera.fill")
                        }
                        .tag(1)

                    ProfileView()
                        .tabItem {
                            Label("Profile", systemImage: "person.fill")
                        }
                        .tag(2)
                }
                .tint(.cxAccent)
            }
        }
        .background(Color.cxBackground)
        .task {
            ensurePlayerExists()
            await seedCatalogIfNeeded()
        }
    }

    private func ensurePlayerExists() {
        if players.isEmpty {
            let player = Player()
            modelContext.insert(player)
            try? modelContext.save()
        }
    }

    private func seedCatalogIfNeeded() async {
        let descriptor = FetchDescriptor<Car>()
        let count = (try? modelContext.fetchCount(descriptor)) ?? 0
        guard count == 0 else { return }
        isSeeding = true
        await CarCatalogService.seed(context: modelContext)
        isSeeding = false
    }
}

struct SeedingView: View {
    @State private var dots = ""
    let timer = Timer.publish(every: 0.5, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "car.fill")
                .font(.system(size: 60))
                .foregroundColor(.cxAccent)

            Text("Building your Cardex\(dots)")
                .font(.title2.weight(.semibold))
                .foregroundColor(.cxTextPrimary)

            Text("Loading 7,000+ cars")
                .font(.subheadline)
                .foregroundColor(.cxTextSecondary)

            ProgressView()
                .tint(.cxAccent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.cxBackground)
        .onReceive(timer) { _ in
            dots = dots.count >= 3 ? "" : dots + "."
        }
    }
}
