import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid

Kirigami.FormLayout {
    id: root

    property alias cfg_stateFilePath:          stateFileField.text
    property alias cfg_refreshIntervalSeconds: refreshSpinBox.value
    property alias cfg_hideClause:             hideClaudeCheck.checked
    property alias cfg_hideCodex:              hideCodexCheck.checked
    property alias cfg_hideCursor:             hideCursorCheck.checked

    QQC2.TextField {
        id: stateFileField
        Kirigami.FormData.label: "State file path:"
        placeholderText: "Default: ~/.local/state/tokenspy/current.json"
        Layout.fillWidth: true
    }

    QQC2.SpinBox {
        id: refreshSpinBox
        Kirigami.FormData.label: "Widget refresh interval (seconds):"
        from: 10
        to: 3600
        stepSize: 10
    }

    Kirigami.Separator {
        Kirigami.FormData.label: "Provider visibility"
        Kirigami.FormData.isSection: true
    }

    QQC2.CheckBox {
        id: hideClaudeCheck
        text: "Hide Claude"
    }

    QQC2.CheckBox {
        id: hideCodexCheck
        text: "Hide Codex"
    }

    QQC2.CheckBox {
        id: hideCursorCheck
        text: "Hide Cursor"
    }
}
