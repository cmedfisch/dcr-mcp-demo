import SwiftUI
import SwiftData

struct CardexFilterSheet: View {
    @Binding var selectedRarity: RarityTier?
    @Binding var showCaughtOnly: Bool
    @Binding var selectedMake: String?
    @Query(sort: \Car.make) private var allCars: [Car]
    @Environment(\.dismiss) private var dismiss

    private var makes: [String] {
        Array(Set(allCars.map(\.make))).sorted()
    }

    var body: some View {
        NavigationStack {
            List {
                Section("Rarity") {
                    ForEach(RarityTier.allCases, id: \.rawValue) { tier in
                        Button {
                            selectedRarity = selectedRarity == tier ? nil : tier
                        } label: {
                            HStack {
                                Image(systemName: tier.icon)
                                    .foregroundStyle(tier.color)
                                Text(tier.name)
                                    .foregroundColor(.cxTextPrimary)
                                Spacer()
                                if selectedRarity == tier {
                                    Image(systemName: "checkmark")
                                        .foregroundColor(.cxAccent)
                                }
                            }
                        }
                    }
                }

                Section("Status") {
                    Toggle("Caught only", isOn: $showCaughtOnly)
                        .tint(.cxAccent)
                }

                Section("Make") {
                    ForEach(makes, id: \.self) { make in
                        Button {
                            selectedMake = selectedMake == make ? nil : make
                        } label: {
                            HStack {
                                Text(make)
                                    .foregroundColor(.cxTextPrimary)
                                Spacer()
                                if selectedMake == make {
                                    Image(systemName: "checkmark")
                                        .foregroundColor(.cxAccent)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Filters")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                        .foregroundColor(.cxAccent)
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button("Reset") {
                        selectedRarity = nil
                        showCaughtOnly = false
                        selectedMake = nil
                    }
                    .foregroundColor(.cxTextSecondary)
                }
            }
        }
    }
}
