import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: root

    property var provider: null

    spacing: 2

    // Provider header
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            source: {
                if (!provider) return ""
                switch (provider.id) {
                    case "claude": return "dialog-messages"
                    case "codex":  return "code-block"
                    case "cursor": return "edit-rename"
                    default:       return "application-x-executable"
                }
            }
            width: Kirigami.Units.iconSizes.small
            height: width
            opacity: provider && provider.status === "ok" ? 1.0 : 0.4
        }

        PlasmaComponents.Label {
            text: provider ? provider.display_name : ""
            font.bold: true
            opacity: provider && provider.status === "ok" ? 1.0 : 0.5
        }

        Item { Layout.fillWidth: true }

        PlasmaComponents.Label {
            visible: provider && provider.status !== "ok" && provider.status !== "disabled"
            text: provider ? provider.status.replace(/_/g, " ") : ""
            color: Kirigami.Theme.negativeTextColor
            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 0.8
        }
    }

    // Error / disabled message
    PlasmaComponents.Label {
        visible: provider && provider.status !== "ok" && provider.status !== "disabled" && provider.error
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
        text: provider && provider.error ? provider.error : ""
        color: Kirigami.Theme.disabledTextColor
        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 0.85
        wrapMode: Text.WordWrap
        elide: Text.ElideRight
        maximumLineCount: 2
    }

    // Window rows (only when ok)
    Repeater {
        model: (provider && provider.status === "ok") ? provider.windows : []

        delegate: RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents.Label {
                text: modelData.label
                color: Kirigami.Theme.disabledTextColor
                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 0.85
                Layout.preferredWidth: 90
                elide: Text.ElideRight
            }

            // Progress bar (drawn as Rectangle for color control)
            Item {
                Layout.fillWidth: true
                height: 6

                Rectangle {
                    anchors.fill: parent
                    radius: 3
                    color: Kirigami.Theme.alternateBackgroundColor
                }
                Rectangle {
                    width: Math.min(modelData.used_pct, 100) / 100.0 * parent.width
                    height: parent.height
                    radius: 3
                    color: {
                        var pct = modelData.used_pct
                        if (pct >= 95) return "#e74c3c"
                        if (pct >= 80) return "#e67e22"
                        if (pct >= 60) return "#f1c40f"
                        return Kirigami.Theme.positiveTextColor
                    }
                    Behavior on width { NumberAnimation { duration: 300 } }
                }
            }

            PlasmaComponents.Label {
                text: Math.min(modelData.used_pct, 100).toFixed(0) + "%"
                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 0.85
                Layout.preferredWidth: 32
                horizontalAlignment: Text.AlignRight
            }

            PlasmaComponents.Label {
                text: formatReset(modelData.resets_at)
                color: Kirigami.Theme.disabledTextColor
                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 0.8
                Layout.preferredWidth: 80
                elide: Text.ElideRight
            }
        }
    }

    function formatReset(isoStr) {
        if (!isoStr) return "—"
        var now = new Date()
        var reset = new Date(isoStr)
        var diffMs = reset - now
        if (diffMs < 0) return "resetting…"
        var diffH = diffMs / 3600000
        if (diffH < 24) {
            var h = Math.floor(diffH)
            var m = Math.floor((diffH - h) * 60)
            return "in " + h + "h " + m + "m"
        }
        return "resets " + reset.toLocaleDateString(Qt.locale(), "ddd d MMM")
    }
}
