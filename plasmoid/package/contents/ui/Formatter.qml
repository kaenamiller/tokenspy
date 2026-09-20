import QtQuick

// Shared text formatting, instantiated by whichever view needs it so the
// wording stays identical between the column-measuring pass and the labels.
QtObject {
    // mode: 2 = roomy ("Tue 22 Sep" / "4h 15m"), 1 = medium ("22 Sep"),
    //       0 = terse ("4d" / "4h")
    function resetText(isoStr, mode) {
        if (!isoStr) return "—"
        var reset = new Date(isoStr)
        var diffMs = reset - new Date()
        if (diffMs < 0) return mode >= 1 ? "resetting…" : "now"
        var diffH = diffMs / 3600000
        if (diffH < 24) {
            var h = Math.floor(diffH)
            var m = Math.floor((diffH - h) * 60)
            if (mode === 0) return h > 0 ? h + "h" : m + "m"
            return h + "h " + m + "m"
        }
        if (mode === 2) return reset.toLocaleDateString(Qt.locale(), "ddd d MMM")
        if (mode === 1) return reset.toLocaleDateString(Qt.locale(), "d MMM")
        return Math.round(diffH / 24) + "d"
    }
}
