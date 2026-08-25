import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui
import "../McpModel.js" as Model

Rectangle {
  id: root
  property var scanData: null
  property color foreground: Color.foreground
  readonly property var entries: Model.diagnosticEntries(scanData)
  signal closed()
  Layout.fillWidth: true
  implicitHeight: content.implicitHeight + Style.space(18)
  color: Qt.alpha(root.foreground, 0.06)
  radius: Style.cornerRadius
  border.width: 1
  border.color: Qt.alpha(Color.accent, 0.35)

  ColumnLayout {
    id: content
    anchors.fill: parent
    anchors.margins: Style.space(9)
    spacing: Style.space(7)

    RowLayout {
      Layout.fillWidth: true
      Text {
        text: "STATIC DIAGNOSTICS · " + root.entries.length
        color: root.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Item { Layout.fillWidth: true }
      Button { text: "×"; tooltipText: "Close diagnostics"; focusable: true; onClicked: root.closed() }
    }

    Text {
      Layout.fillWidth: true
      text: "Configuration findings only. MCP Manager has not started a server or tested connectivity."
      color: Qt.alpha(root.foreground, 0.72)
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
      wrapMode: Text.WordWrap
    }

    Text {
      visible: root.entries.length === 0
      text: "No static diagnostics were found."
      color: Qt.alpha(root.foreground, 0.72)
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
    }

    Repeater {
      model: root.entries
      ColumnLayout {
        id: diagnosticEntry
        required property var modelData
        required property int index
        Layout.fillWidth: true
        spacing: Style.space(4)

        Text {
          visible: diagnosticEntry.index === 0 || root.entries[diagnosticEntry.index - 1].severity !== diagnosticEntry.modelData.severity
          text: String(diagnosticEntry.modelData.severity || "info").toUpperCase()
          color: Qt.alpha(root.foreground, 0.62)
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
          font.bold: true
          font.letterSpacing: 0.7
          Layout.topMargin: Style.space(4)
        }

        Rectangle {
          Layout.fillWidth: true
          implicitHeight: cardContent.implicitHeight + Style.space(14)
          color: Qt.alpha(root.foreground, 0.035)
          radius: Style.cornerRadius
          border.width: 1
          border.color: Qt.alpha(root.foreground, 0.14)

          ColumnLayout {
            id: cardContent
            anchors.fill: parent
            anchors.margins: Style.space(7)
            spacing: Style.space(3)
            RowLayout {
              Layout.fillWidth: true
              DiagnosticBadge { label: String(diagnosticEntry.modelData.severity || "info"); severity: String(diagnosticEntry.modelData.severity || "info"); foreground: root.foreground }
              Text { Layout.fillWidth: true; text: String(diagnosticEntry.modelData.label || "Diagnostic"); color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true; wrapMode: Text.WordWrap }
            }
            Text {
              Layout.fillWidth: true
              text: String(diagnosticEntry.modelData.agentName || "General")
                + (diagnosticEntry.modelData.sourceName ? " · " + String(diagnosticEntry.modelData.sourceName) : "")
                + (diagnosticEntry.modelData.serverName ? " · " + String(diagnosticEntry.modelData.serverName) : "")
              color: Qt.alpha(root.foreground, 0.68)
              font.family: "monospace"
              font.pixelSize: Style.font.caption
              elide: Text.ElideMiddle
            }
            Text { Layout.fillWidth: true; text: String(diagnosticEntry.modelData.guidance || ""); color: Qt.alpha(root.foreground, 0.76); font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
          }
        }
      }
    }
  }
}
