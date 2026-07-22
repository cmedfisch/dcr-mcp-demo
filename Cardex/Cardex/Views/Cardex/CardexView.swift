import SwiftUI
import SwiftData

struct CardexView: View {
    @Query(sort: \Car.make) private var allCars: [Car]
    @State private var searchText = ""
    @State private var selectedRarity: RarityTier?
    @State private var showCaughtOnly = false

    private var filteredCars: [Car] {
        allCars.filter { car in
            if showCaughtOnly && !car.isCaught { return false }
            if let rarity = selectedRarity, car.rarityTier != rarity.rawValue { return false }
            if !searchText.isEmpty {
                let query = searchText.lowercased()
                return car.make.lowercased().contains(query)
                    || car.model.lowercased().contains(query)
                    || car.generation.lowercased().contains(query)
            }
            return true
        }
    }

    private let columns = [
        GridItem(.flexible(), spacing: 8),
        GridItem(.flexible(), spacing: 8),
        GridItem(.flexible(), spacing: 8),
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    SearchBar(text: $searchText, placeholder: "Search make, model...")
                        .padding(.horizontal)

                    filterChips
                        .padding(.horizontal)

                    statsRow
                        .padding(.horizontal)

                    LazyVGrid(columns: columns, spacing: 8) {
                        ForEach(filteredCars) { car in
                            NavigationLink(value: car) {
                                CardexGridItem(car: car)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal)
                }
                .padding(.vertical)
            }
            .background(Color.cxBackground)
            .navigationTitle("Cardex")
            .navigationDestination(for: Car.self) { car in
                CarDetailView(car: car)
            }
        }
    }

    private var filterChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                FilterChip(title: "All", isSelected: selectedRarity == nil && !showCaughtOnly) {
                    selectedRarity = nil
                    showCaughtOnly = false
                }
                FilterChip(title: "Caught", isSelected: showCaughtOnly) {
                    showCaughtOnly.toggle()
                }
                ForEach(RarityTier.allCases, id: \.rawValue) { tier in
                    FilterChip(title: tier.name, isSelected: selectedRarity == tier, color: tier.color) {
                        selectedRarity = selectedRarity == tier ? nil : tier
                    }
                }
            }
        }
    }

    private var statsRow: some View {
        let caught = allCars.filter(\.isCaught).count
        let total = allCars.count
        return HStack {
            Text("\(caught)/\(total) caught")
                .font(.caption)
                .foregroundColor(.cxTextSecondary)
            Spacer()
            Text("\(filteredCars.count) shown")
                .font(.caption)
                .foregroundColor(.cxTextSecondary)
        }
    }
}

struct FilterChip: View {
    let title: String
    let isSelected: Bool
    var color: Color = .cxAccent
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.caption.weight(.medium))
                .foregroundStyle(isSelected ? .white : .cxTextSecondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(
                    Capsule()
                        .fill(isSelected ? color : Color.cxSurfaceLight)
                )
        }
    }
}
