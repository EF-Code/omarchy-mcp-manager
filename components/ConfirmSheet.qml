import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Rectangle {
  id: root
  property var preview: null
  property string title: "Confirm change"
  property color foreground: Color.foreground
  signal confirmed()
  signal cancelled()
  Layout.fillWidth: true
  implicitHeight: sheet.implicitHeight + Style.space(18)
  color: Qt.alpha(Color.accent, 0.10)
  radius: Style.cornerRadius
  border.width: 1
  border.color: Qt.alpha(Color.accent, 0.45)

  ColumnLayout {
    id: sheet
    anchors.fill: parent
    anchors.margins: Style.space(9)
    spacing: Style.space(8)
    Text { text: root.title; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
    DiffPreview { Layout.fillWidth: true; preview: root.preview; foreground: root.foreground }
    RowLayout {
      Layout.fillWidth: true
      Item { Layout.fillWidth: true }
      Button { text: "Cancel"; focusable: true; onClicked: root.cancelled() }
      Button { text: "Apply"; focusable: true; onClicked: root.confirmed() }
    }
  }
}
