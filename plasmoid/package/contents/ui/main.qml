import QtQuick
import QtQuick.Layouts
import QtCore
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as PlasmaSupport

PlasmoidItem {
    id: root

    property var snapshot: null
    property string fetchError: ""

    readonly property int refreshIntervalMs: Math.max(10, Plasmoid.configuration.refreshIntervalSeconds || 30) * 1000

    readonly property string stateFilePath: {
        var custom = Plasmoid.configuration.stateFilePath
        if (custom && custom !== "") return custom
        var home = StandardPaths.writableLocation(StandardPaths.HomeLocation).toString()
        home = home.replace(/^file:\/\//, "")
        return home + "/.local/state/tokenspy/current.json"
    }

    toolTipMainText: "TokenSpy"
    toolTipSubText: {
        if (fetchError !== "") return fetchError
        if (!snapshot) return "Loading…"
        var maxPct = 0
        for (var i = 0; i < snapshot.providers.length; i++) {
            var p = snapshot.providers[i]
            for (var j = 0; j < p.windows.length; j++) {
                if (p.windows[j].used_pct > maxPct) maxPct = p.windows[j].used_pct
            }
        }
        return Math.min(maxPct, 100).toFixed(0) + "% peak usage"
    }

    PlasmaSupport.DataSource {
        id: stateSource
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            disconnectSource(sourceName)
            var text = (data["stdout"] || "").trim()
            if (text === "") {
                fetchError = "State file not found — start the daemon: systemctl --user start tokenspyd"
                return
            }
            try {
                snapshot = JSON.parse(text)
                fetchError = ""
            } catch (e) {
                fetchError = "State file is malformed — run: systemctl --user restart tokenspyd"
            }
        }
    }

    function refresh() {
        stateSource.connectSource("cat -- " + shellQuote(stateFilePath))
    }

    function shellQuote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'"
    }

    Timer {
        id: refreshTimer
        interval: root.refreshIntervalMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    Connections {
        target: Plasmoid.configuration
        function onRefreshIntervalSecondsChanged() {
            refreshTimer.interval = root.refreshIntervalMs
        }
    }

    compactRepresentation: CompactView {
        snapshot: root.snapshot
        fetchError: root.fetchError
    }

    fullRepresentation: FullView {
        snapshot: root.snapshot
        fetchError: root.fetchError
        hideClaude: Plasmoid.configuration.hideClause
        hideCodex: Plasmoid.configuration.hideCodex
        hideCursor: Plasmoid.configuration.hideCursor
    }
}
