/**
 * WidgetLayer — renders all open floating widgets.
 * Lives on top of App.tsx content, below modals.
 */

import { useStore } from '../store/useStore'
import WeatherWidget from '../widgets/WeatherWidget'
import SystemWidget from '../widgets/SystemWidget'
import TerminalWidget from '../widgets/TerminalWidget'
import ToolsWidget from '../widgets/ToolsWidget'
import MapWidget from '../widgets/MapWidget'
import StockWidget from '../widgets/StockWidget'
import EmailWidget from '../widgets/EmailWidget'
import ResearchWidget from '../widgets/ResearchWidget'
import CodeEditorWidget from '../widgets/CodeEditorWidget'
import KnowledgeWidget from '../widgets/KnowledgeWidget'
import SecurityWidget from '../widgets/SecurityWidget'
import MemoryWidget from '../widgets/MemoryWidget'

const WIDGET_COMPONENTS: Record<string, React.ComponentType<{ widget: any }>> = {
  weather: WeatherWidget,
  system: SystemWidget,
  terminal: TerminalWidget,
  tools: ToolsWidget,
  map: MapWidget,
  stock: StockWidget,
  email: EmailWidget,
  research: ResearchWidget,
  'code-editor': CodeEditorWidget,
  knowledge: KnowledgeWidget,
  security: SecurityWidget,
  memory: MemoryWidget,
}

export default function WidgetLayer() {
  const widgets = useStore((s) => s.widgets)

  return (
    <>
      {widgets.map((widget) => {
        const Component = WIDGET_COMPONENTS[widget.type]
        if (!Component) return null
        return <Component key={widget.id} widget={widget} />
      })}
    </>
  )
}
