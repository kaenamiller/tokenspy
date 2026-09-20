import QtQuick
import org.kde.kirigami as Kirigami

// Usage meter drawn as plain Rectangles so the fill colour can track the
// percentage rather than the theme's single highlight colour.
Item {
    id: bar

    property real percent: 0

    readonly property real clamped: Math.max(0, Math.min(percent, 100))

    implicitHeight: Math.max(4, Math.round(Kirigami.Units.gridUnit * 0.35))
    implicitWidth: Kirigami.Units.gridUnit * 4

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Kirigami.Theme.alternateBackgroundColor
    }

    Rectangle {
        width: bar.clamped / 100.0 * parent.width
        height: parent.height
        radius: height / 2
        color: {
            if (bar.clamped >= 95) return "#e74c3c"
            if (bar.clamped >= 80) return "#e67e22"
            if (bar.clamped >= 60) return "#f1c40f"
            return Kirigami.Theme.positiveTextColor
        }
        Behavior on width { NumberAnimation { duration: 300 } }
    }
}
