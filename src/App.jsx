import { useState } from 'react'
import ProjectsDashboard from './components/ProjectsDashboard'
import ProjectWorkspace from './components/ProjectWorkspace'
import { DashboardIcon, ProjectIcon, DocumentIcon, StoryIcon, EpicIcon, AnalyticsIcon, AiIcon, SettingsIcon } from './components/Icons'

function App() {
  const [activeProjectId, setActiveProjectId] = useState(null)

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">CL</div>
          <div>
            <h2>Clarity Labs</h2>
            <p>Enterprise Plan</p>
          </div>
        </div>
        <ul className="sidebar-menu">
          <li className={`sidebar-item ${!activeProjectId ? 'active' : ''}`} onClick={() => setActiveProjectId(null)}>
            <div style={{width: 20, display: 'flex', justifyContent: 'center'}}><DashboardIcon size={18} /></div> Dashboard
          </li>
          <li className={`sidebar-item ${activeProjectId ? 'active' : ''}`}>
            <div style={{width: 20, display: 'flex', justifyContent: 'center'}}><ProjectIcon size={18} /></div> Projects
          </li>
          <li className="sidebar-item">
            <div style={{width: 20, display: 'flex', justifyContent: 'center'}}><DocumentIcon size={18} /></div> Documents
          </li>
          <li className="sidebar-item">
            <div style={{width: 20, display: 'flex', justifyContent: 'center'}}><StoryIcon size={18} /></div> Stories
          </li>
          <li className="sidebar-item">
            <div style={{width: 20, display: 'flex', justifyContent: 'center'}}><EpicIcon size={18} /></div> Epics
          </li>
          <li className="sidebar-item">
            <div style={{width: 20, display: 'flex', justifyContent: 'center'}}><AnalyticsIcon size={18} /></div> Analytics
          </li>
          <li className="sidebar-item">
            <div style={{width: 20, display: 'flex', justifyContent: 'center'}}><AiIcon size={18} /></div> AI Assistant
          </li>
          <li className="sidebar-item" style={{marginTop: 'auto'}}>
            <div style={{width: 20, display: 'flex', justifyContent: 'center'}}><SettingsIcon size={18} /></div> Settings
          </li>
        </ul>
      </aside>
      
      {/* Main Workspace Content */}
      <main className="workspace">
        {!activeProjectId ? (
          <ProjectsDashboard onOpenWorkspace={setActiveProjectId} />
        ) : (
          <ProjectWorkspace projectId={activeProjectId} />
        )}
      </main>
    </div>
  )
}

export default App
