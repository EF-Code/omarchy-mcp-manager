import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Rectangle {
  id: root
  property var comparison: null
  property color foreground: Color.foreground
  signal closed()
  Layout.fillWidth: true
  implicitHeight: matrix.implicitHeight + Style.space(16)
  color: Qt.alpha(root.foreground, 0.06)
  radius: Style.cornerRadius
  border.width: 1
  border.color: Qt.alpha(Color.accent, 0.35)

  Button {
    anchors.top: parent.top
    anchors.right: parent.right
    anchors.margins: Style.space(6)
    z: 2
    text: "×"
    tooltipText: "Close comparison"
    focusable: true
    onClicked: root.closed()
  }

  ColumnLayout {
    id: matrix
    anchors.fill: parent
    anchors.margins: Style.space(8)
    spacing: Style.space(5)
    RowLayout {
      Layout.fillWidth: true
      Text { text: "CROSS-AGENT COMPARISON"; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption; font.bold: true }
      Item { Layout.fillWidth: true }
    }
    RowLayout {
      Layout.fillWidth: true
      Item { Layout.preferredWidth: Style.space(150) }
      Repeater {
        model: root.comparison && Array.isArray(root.comparison.agents) ? root.comparison.agents : []
        Text {
          required property var modelData
          text: String(modelData.agentName || modelData.agentId || "Agent")
          color: Qt.alpha(root.foreground, 0.72)
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
          Layout.preferredWidth: Style.space(70)
          elide: Text.ElideRight
        }
      }
    }
    Repeater {
      model: root.comparison && Array.isArray(root.comparison.serverNames) ? root.comparison.serverNames : []
      RowLayout {
        id: matrixRow
        required property string modelData
        property string rowName: modelData
        Layout.fillWidth: true
        Text { text: modelData; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption; Layout.preferredWidth: Style.space(150); elide: Text.ElideRight }
        Repeater {
          model: root.comparison && Array.isArray(root.comparison.agents) ? root.comparison.agents : []
          Text {
            required property var modelData
            text: modelData.servers && modelData.servers[matrixRow.rowName] ? (modelData.servers[matrixRow.rowName].state === "enabled" ? "●" : "○") : "—"
            color: Qt.alpha(root.foreground, 0.7)
            font.pixelSize: Style.font.caption
            Layout.preferredWidth: Style.space(70)
          }
        }
      }
    }
    Text { Layout.fillWidth: true; text: "Enabled, disabled, and missing cells are static configuration states, not connectivity results."; color: Qt.alpha(root.foreground, 0.7); font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
  }
}
