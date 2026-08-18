import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.kirigami as Kirigami

Item {
    id: root

    property var snapshot: null
    property string fetchError: ""

    readonly property real maxUsedPct: {
        if (!snapshot) return -1
        var max = 0
        for (var i = 0; i < snapshot.providers.length; i++) {
            var p = snapshot.providers[i]
            for (var j = 0; j < p.windows.length; j++) {
                if (p.windows[j].used_pct > max) max = p.windows[j].used_pct
            }
        }
        return Math.min(max, 100)
    }

    readonly property color usageColor: {
        if (maxUsedPct < 0 || fetchError !== "") return Kirigami.Theme.disabledTextColor
        if (maxUsedPct >= 95) return "#e74c3c"
        if (maxUsedPct >= 80) return "#e67e22"
        if (maxUsedPct >= 60) return "#f1c40f"
        return Kirigami.Theme.positiveTextColor
    }

    RowLayout {
        anchors.centerIn: parent
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            source: "view-statistics"
            width: Kirigami.Units.iconSizes.smallMedium
            height: width
            color: root.usageColor
        }

        PlasmaComponents.Label {
            visible: maxUsedPct >= 0 && fetchError === ""
            text: maxUsedPct.toFixed(0) + "%"
            color: root.usageColor
            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 0.9
        }

        Kirigami.Icon {
            visible: fetchError !== ""
            source: "data-warning"
            width: Kirigami.Units.iconSizes.smallMedium
            height: width
        }
    }
}
