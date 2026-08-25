import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qs.Commons

Flickable {
  id: root
  property var agents: []
  property int selectedIndex: 0
  property color foreground: Color.foreground
  signal selected(int index)
  Layout.preferredHeight: Style.space(160)
  Layout.minimumHeight: Style.space(120)
  Layout.maximumHeight: Style.space(160)
  Layout.minimumWidth: 0
  clip: true
  contentWidth: width
  contentHeight: railColumn.implicitHeight
  boundsBehavior: Flickable.StopAtBounds
  ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

  ColumnLayout {
    id: railColumn
    width: root.width
    spacing: Style.space(4)
    Repeater {
      model: root.agents
      AgentCard {
        required property var modelData
        required property int index
        agent: modelData
        selected: index === root.selectedIndex
        foreground: root.foreground
        onChosen: root.selected(index)
      }
    }
  }
}
