import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.components as PlasmaComponents
import org.kde.kirigami as Kirigami

Item {
    id: root

    property var snapshot: null
    property string fetchError: ""
    property bool hideClaude: false
    property bool hideCodex: false
    property bool hideCursor: false
    property bool hideOpenCodeGo: false

    readonly property real gu: Kirigami.Units.gridUnit
    readonly property real edgeMargin: gu * 0.75

    implicitWidth: gu * 22
    implicitHeight: gu * 15

    Layout.minimumWidth: gu * 11
    Layout.minimumHeight: gu * 6

    Formatter { id: sharedFormatter }

    FontMetrics {
        id: rowMetrics
        font.family: Kirigami.Theme.defaultFont.family
        font.pixelSize: Math.round(Kirigami.Theme.defaultFont.pixelSize * 0.85)
    }

    // Provider mark sized against the header text rather than
    // Kirigami.Units.iconSizes.small, which scales with font DPI and was
    // rendering at roughly twice the label's cap height.
    readonly property real iconSize: Math.round(Kirigami.Theme.defaultFont.pixelSize)

    // --- Shared column geometry -------------------------------------------
    // Measured once across every visible window so all providers share one
    // grid, and so the text columns are served before the bar rather than
    // after it. The old fixed 90/32/80px columns truncated their contents no
    // matter how much width the widget was given.

    readonly property var allWindows: {
        var out = []
        if (!snapshot || !snapshot.providers) return out
        for (var i = 0; i < snapshot.providers.length; i++) {
            var p = snapshot.providers[i]
            if (p.status !== "ok" || _hidden(p.id)) continue
            for (var j = 0; j < p.windows.length; j++) out.push(p.windows[j])
        }
        return out
    }

    readonly property var columns: {
        var indent = iconSize + Kirigami.Units.smallSpacing
        var spacing = Kirigami.Units.smallSpacing
        var rowWidth = Math.max(0, contentWidth - indent)
        var minBar = gu * 4

        var labelNatural = 0
        for (var i = 0; i < allWindows.length; i++) {
            labelNatural = Math.max(labelNatural,
                                    rowMetrics.advanceWidth(allWindows[i].label))
        }
        labelNatural = Math.ceil(labelNatural) + 2
        // One long label ("On-demand spend") must not swallow the whole row.
        var labelWidth = Math.min(labelNatural, Math.max(gu * 4, rowWidth * 0.40))
        var pctWidth = Math.ceil(rowMetrics.advanceWidth("100%")) + 2

        function resetWidth(mode) {
            var w = 0
            for (var k = 0; k < allWindows.length; k++) {
                w = Math.max(w, rowMetrics.advanceWidth(
                    sharedFormatter.resetText(allWindows[k].resets_at, mode)))
            }
            return Math.ceil(w) + 2
        }

        // Below this the four columns cannot coexist on one line, so window
        // rows stack the bar under the label instead.
        var narrow = rowWidth > 0 && rowWidth < gu * 15

        // Pick the most informative reset format the leftover space allows.
        var mode = 2
        if (!narrow) {
            var budget = rowWidth - labelWidth - pctWidth - minBar - spacing * 3
            if (resetWidth(2) > budget) mode = (resetWidth(1) <= budget) ? 1 : 0
        }

        return {
            "font": rowMetrics.font,
            "iconSize": iconSize,
            "indent": indent,
            "narrow": narrow,
            "labelWidth": labelWidth,
            "pctWidth": pctWidth,
            "resetMode": mode,
            "resetWidth": resetWidth(mode),
            "minBarWidth": minBar
        }
    }

    // Width reserved for the scrollbar. The attached ScrollBar anchors to the
    // Flickable's right edge, so this is subtracted from the content width
    // rather than from the Flickable, which would push the bar inward and
    // leave dead space outside it. Always reserved so the columns don't
    // reflow when the bar appears.
    readonly property real scrollGutter: verticalScrollBar.implicitWidth
                                         + Kirigami.Units.smallSpacing

    // Published separately so `columns` depends on a plain number rather than
    // on the layout it feeds, which would be a binding loop.
    readonly property real contentWidth: flickable.width - root.scrollGutter

    // A plain Flickable rather than a ScrollView: a ScrollView derives its own
    // implicit height from its content item, so sizing the content against the
    // viewport closes a binding loop. A Flickable's geometry comes only from
    // its anchors, so contentHeight can safely reference it.
    Flickable {
        id: flickable
        anchors.fill: parent
        anchors.margins: root.edgeMargin
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        contentWidth: width
        // Stretch to the viewport when the providers fit (so the block stays
        // vertically centred) and past it when they don't, so the list scrolls
        // instead of being silently clipped.
        contentHeight: Math.max(contentColumn.implicitHeight, height)

        QQC2.ScrollBar.vertical: QQC2.ScrollBar {
            id: verticalScrollBar
            policy: flickable.contentHeight > flickable.height
                    ? QQC2.ScrollBar.AlwaysOn : QQC2.ScrollBar.AlwaysOff
        }

        ColumnLayout {
            id: contentColumn
            y: Math.max(0, (flickable.height - implicitHeight) / 2)
            width: flickable.width - root.scrollGutter
            spacing: Kirigami.Units.gridUnit * 0.5

            // Daemon-not-running banner
            Rectangle {
                visible: fetchError !== ""
                Layout.fillWidth: true
                Layout.preferredHeight: errorRow.implicitHeight + Kirigami.Units.gridUnit
                radius: Kirigami.Units.cornerRadius
                color: Kirigami.Theme.negativeBackgroundColor

                RowLayout {
                    id: errorRow
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.smallSpacing
                    spacing: Kirigami.Units.smallSpacing

                    Kirigami.Icon {
                        source: "data-warning"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    }

                    PlasmaComponents.Label {
                        Layout.fillWidth: true
                        text: root.fetchError
                        wrapMode: Text.WordWrap
                        color: Kirigami.Theme.negativeTextColor
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 0.85
                    }
                }
            }

            // Loading state
            PlasmaComponents.Label {
                visible: !fetchError && !snapshot
                Layout.fillWidth: true
                text: "Loading…"
                color: Kirigami.Theme.disabledTextColor
                horizontalAlignment: Text.AlignHCenter
            }

            // Provider rows
            Repeater {
                model: snapshot ? snapshot.providers : []

                delegate: ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    ProviderRow {
                        Layout.fillWidth: true
                        provider: modelData
                        columns: root.columns
                        formatter: sharedFormatter
                        visible: modelData.status !== "disabled" && !_hidden(modelData.id)
                    }

                    Kirigami.Separator {
                        Layout.fillWidth: true
                        Layout.topMargin: Kirigami.Units.smallSpacing
                        visible: index < snapshot.providers.length - 1
                                 && modelData.status !== "disabled"
                                 && !_hidden(modelData.id)
                        opacity: 0.3
                    }
                }
            }

            // Last updated
            PlasmaComponents.Label {
                visible: snapshot !== null
                Layout.fillWidth: true
                text: snapshot ? "Updated " + _formatAge(snapshot.generated_at) : ""
                color: Kirigami.Theme.disabledTextColor
                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 0.75
                horizontalAlignment: Text.AlignRight
            }
        }
    }

    function _hidden(providerId) {
        if (providerId === "claude" && hideClaude) return true
        if (providerId === "codex"  && hideCodex)  return true
        if (providerId === "cursor" && hideCursor)  return true
        if (providerId === "opencode-go" && hideOpenCodeGo) return true
        return false
    }

    function _formatAge(isoStr) {
        if (!isoStr) return ""
        var then = new Date(isoStr)
        var diffS = Math.floor((new Date() - then) / 1000)
        if (diffS < 60) return "just now"
        if (diffS < 3600) return Math.floor(diffS / 60) + "m ago"
        return Math.floor(diffS / 3600) + "h ago"
    }
}
