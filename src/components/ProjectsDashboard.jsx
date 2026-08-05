import { useState, useEffect } from 'react'
import CreateProjectModal from './CreateProjectModal'
import { PlusIcon, TrashIcon } from './Icons'

export default function ProjectsDashboard({ onOpenWorkspace }) {
  const [projects, setProjects] = useState([])
  const [isModalOpen, setIsModalOpen] = useState(false)

  const loadProjects = async () => {
    try {
      const res = await fetch('/api/v1/projects')
      const data = await res.json()
      setProjects(data.projects || [])
    } catch (err) {
      console.error('Failed to load projects', err)
    }
  }

  useEffect(() => {
    loadProjects()
  }, [])

  const handleDelete = async (pid) => {
    if (!window.confirm(`Are you sure you want to delete Project ${pid}? This cannot be undone.`)) return
    try {
      const res = await fetch(`/api/v1/projects/${pid}`, { method: 'DELETE' })
      if (res.ok) {
        loadProjects()
      }
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h2>Projects Dashboard</h2>
          <p className="subtitle" style={{marginTop: '4px'}}>Select an existing project or configure a new project tech stack.</p>
        </div>
        <button className="btn-primary" onClick={() => setIsModalOpen(true)}>
          <PlusIcon size={16} /> Create Project
        </button>
      </div>

      <div className="projects-grid">
        {projects.length === 0 && (
          <div className="project-card" style={{ gridColumn: '1 / -1', textAlign: 'center' }}>
            <h4>No Existing Projects Found</h4>
            <p className="text-muted">You haven't created any projects yet.</p>
          </div>
        )}
        
        {projects.map(p => (
          <div key={p.config.projectId} className="project-card">
            <div className="card-title-row">
              <span className="pid-tag">{p.config.projectId}</span>
              <h4>{p.config.projectName}</h4>
            </div>
            <p style={{ color: 'var(--text-muted)' }}>
              {p.config.framework} • {p.config.language} • {p.config.cssStrategy} • {p.config.folderStructure}
            </p>
            <div className="card-footer">
              <span>{p.storyCount} Stories</span>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button 
                  className="btn-secondary" 
                  style={{ borderColor: 'var(--status-error-text)', color: 'var(--status-error-text)' }}
                  onClick={() => handleDelete(p.config.projectId)}
                >
                  <TrashIcon size={16} />
                </button>
                <button 
                  className="btn-secondary" 
                  onClick={() => onOpenWorkspace(p.config.projectId)}
                >
                  Open Workspace →
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {isModalOpen && (
        <CreateProjectModal 
          onClose={() => setIsModalOpen(false)} 
          onSuccess={(pid) => {
            setIsModalOpen(false)
            onOpenWorkspace(pid)
          }} 
        />
      )}
    </div>
  )
}
