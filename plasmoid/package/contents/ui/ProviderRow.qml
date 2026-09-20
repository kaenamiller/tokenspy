import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: root

    property var provider: null

    // Column geometry is decided once for the whole widget and handed down, so
    // every provider's bars line up on the same grid.
    property var columns: null
    property var formatter: null

    readonly property real iconSize: columns ? columns.iconSize
                                             : Kirigami.Units.iconSizes.small
    readonly property real indent: columns ? columns.indent
                                           : iconSize + Kirigami.Units.smallSpacing

    spacing: 2

    // Provider header
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            // Bundled marks rather than freedesktop icon names, which resolved
            // to unrelated Breeze glyphs (OpenCode Go was getting a hammer).
            source: {
                if (!provider) return ""
                switch (provider.id) {
                    case "claude":      return Qt.resolvedUrl("../icons/claude.svg")
                    case "codex":       return Qt.resolvedUrl("../icons/codex.svg")
                    case "cursor":      return Qt.resolvedUrl("../icons/cursor.svg")
                    case "opencode-go": return Qt.resolvedUrl("../icons/opencode-go.svg")
                    default:            return "application-x-executable"
                }
            }
            // The marks are single-colour silhouettes, so tint them with the
            // theme text colour to track light and dark themes.
            isMask: true
            color: Kirigami.Theme.textColor
            // Layout hints, not width/height: inside a RowLayout the plain
            // geometry properties are overridden and the icon falls back to
            // Kirigami's default implicit size.
            implicitWidth: root.iconSize
            implicitHeight: root.iconSize
            Layout.preferredWidth: root.iconSize
            Layout.preferredHeight: root.iconSize
            opacity: provider && provider.status === "ok" ? 1.0 : 0.4
        }

        PlasmaComponents.Label {
            Layout.fillWidth: true
            text: provider ? provider.display_name : ""
            font.bold: true
            elide: Text.ElideRight
            opacity: provider && provider.status === "ok" ? 1.0 : 0.5
        }

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
        Layout.leftMargin: root.indent
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

        delegate: ColumnLayout {
            id: windowRow

            Layout.fillWidth: true
            Layout.leftMargin: root.indent
            Layout.topMargin: (root.columns && root.columns.narrow)
                              ? Kirigami.Units.smallSpacing / 2 : 0
            spacing: 2

            readonly property string resetText: (root.formatter && root.columns)
                ? root.formatter.resetText(modelData.resets_at, root.columns.resetMode)
                : ""

            // Wide form: label | bar | percent | reset
            RowLayout {
                Layout.fillWidth: true
                visible: root.columns && !root.columns.narrow
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents.Label {
                    text: modelData.label
                    color: Kirigami.Theme.disabledTextColor
                    font: root.columns ? root.columns.font : Kirigami.Theme.defaultFont
                    Layout.preferredWidth: root.columns ? root.columns.labelWidth : 0
                    elide: Text.ElideRight
                }

                UsageBar {
                    percent: modelData.used_pct
                    Layout.fillWidth: true
                    Layout.minimumWidth: root.columns ? root.columns.minBarWidth : 0
                    Layout.preferredHeight: implicitHeight
                }

                PlasmaComponents.Label {
                    text: Math.min(modelData.used_pct, 100).toFixed(0) + "%"
                    font: root.columns ? root.columns.font : Kirigami.Theme.defaultFont
                    Layout.preferredWidth: root.columns ? root.columns.pctWidth : 0
                    horizontalAlignment: Text.AlignRight
                }

                PlasmaComponents.Label {
                    text: windowRow.resetText
                    color: Kirigami.Theme.disabledTextColor
                    font: root.columns ? root.columns.font : Kirigami.Theme.defaultFont
                    Layout.preferredWidth: root.columns ? root.columns.resetWidth : 0
                    horizontalAlignment: Text.AlignRight
                }
            }

            // Narrow form: label + percent + reset on one line, bar beneath
            RowLayout {
                Layout.fillWidth: true
                visible: root.columns && root.columns.narrow
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents.Label {
                    Layout.fillWidth: true
                    text: modelData.label
                    color: Kirigami.Theme.disabledTextColor
                    font: root.columns ? root.columns.font : Kirigami.Theme.defaultFont
                    elide: Text.ElideRight
                }

                PlasmaComponents.Label {
                    text: Math.min(modelData.used_pct, 100).toFixed(0) + "%"
                    font: root.columns ? root.columns.font : Kirigami.Theme.defaultFont
                }

                PlasmaComponents.Label {
                    text: windowRow.resetText
                    color: Kirigami.Theme.disabledTextColor
                    font: root.columns ? root.columns.font : Kirigami.Theme.defaultFont
                    elide: Text.ElideRight
                }
            }

            UsageBar {
                visible: root.columns && root.columns.narrow
                percent: modelData.used_pct
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
            }
        }
    }
}
