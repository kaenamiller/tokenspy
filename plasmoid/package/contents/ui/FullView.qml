import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents
import org.kde.kirigami as Kirigami

Item {
    id: root

    property var snapshot: null
    property string fetchError: ""
    property bool hideClaude: false
    property bool hideCodex: false
    property bool hideCursor: false

    implicitWidth: Kirigami.Units.gridUnit * 22
    implicitHeight: Kirigami.Units.gridUnit * 15

    ColumnLayout {
        id: contentColumn
        readonly property real edgeMargin: Kirigami.Units.gridUnit * 0.75
        anchors {
            horizontalCenter: parent.horizontalCenter
            verticalCenter: parent.verticalCenter
        }
        width: parent.width - edgeMargin * 2
        // Keep the natural compact layout, but explicitly place that block in
        // the middle of tall widget containers.
        height: Math.min(implicitHeight, parent.height - edgeMargin * 2)
        spacing: Kirigami.Units.gridUnit * 0.5

        // Daemon-not-running banner
        Rectangle {
            visible: fetchError !== ""
            Layout.fillWidth: true
            height: errorLabel.implicitHeight + Kirigami.Units.gridUnit
            radius: Kirigami.Units.cornerRadius
            color: Kirigami.Theme.negativeBackgroundColor

            RowLayout {
                anchors.centerIn: parent
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: Kirigami.Units.smallSpacing
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Icon {
                    source: "data-warning"
                    width: Kirigami.Units.iconSizes.small
                    height: width
                }

                PlasmaComponents.Label {
                    id: errorLabel
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
                    visible: modelData.status !== "disabled" && !_hidden(modelData.id)
                }

                Kirigami.Separator {
                    Layout.fillWidth: true
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

    function _hidden(providerId) {
        if (providerId === "claude" && hideClaude) return true
        if (providerId === "codex"  && hideCodex)  return true
        if (providerId === "cursor" && hideCursor)  return true
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
