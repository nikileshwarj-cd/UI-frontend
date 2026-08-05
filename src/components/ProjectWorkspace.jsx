import { useState, useEffect, useRef } from 'react'
import mermaid from 'mermaid'
import { FileIcon } from './Icons'

export default function ProjectWorkspace({ projectId }) {
  const [project, setProject] = useState(null)
  const [activeTab, setActiveTab] = useState('graph')
  const [userStory, setUserStory] = useState('')
  const [wireframeFile, setWireframeFile] = useState(null)
  
  const mermaidRef = useRef(null)

  const loadProjectData = async () => {
    try {
      const res = await fetch(`/api/v1/projects/${projectId}`)
      const data = await res.json()
      setProject(data)
    } catch (err) {
      console.error(err)
    }
  }

  useEffect(() => {
    loadProjectData()
  }, [projectId])

  useEffect(() => {
    if (activeTab === 'graph' && project?.storyGraph?.stories && mermaidRef.current) {
      const stories = project.storyGraph.stories
      if (stories.length === 0) {
        mermaidRef.current.innerHTML = 'graph TD;\n  Start[Add Your First User Story]'
        return
      }
      
      let lines = ['graph TD;']
      lines.push('classDef node fill:#1e293b,stroke:#38bdf8,color:#f8fafc;')
      
      stories.forEach(s => {
        lines.push(`  ${s.id}["${s.id}: ${s.component}"]:::node;`)
        if (s.dependsOn && s.dependsOn.length > 0) {
          s.dependsOn.forEach(depId => {
            lines.push(`  ${depId} --> ${s.id};`)
          })
        }
      })
      
      const code = lines.join('\n')
      mermaidRef.current.innerHTML = code
      mermaidRef.current.removeAttribute('data-processed')
      try {
        mermaid.contentLoaded()
      } catch (e) {
        console.error('Mermaid render error:', e)
      }
    }
  }, [project, activeTab])

  const handleAddStory = async (e) => {
    e.preventDefault()
    if (!wireframeFile) {
      alert('A Wireframe image is mandatory.')
      return
    }

    const formData = new FormData()
    formData.append('userStory', userStory)
    formData.append('wireframe', wireframeFile)

    try {
      const res = await fetch(`/api/v1/projects/${projectId}/stories`, {
        method: 'POST',
        body: formData
      })
      if (res.ok) {
        setUserStory('')
        setWireframeFile(null)
        loadProjectData()
      } else {
        alert('Failed to generate story')
      }
    } catch (err) {
      console.error(err)
    }
  }

  if (!project) return <div>Loading Workspace...</div>

  return (
    <div>
      <div className="workspace-banner">
        <div className="card-title-row">
          <span className="pid-tag">{project.config.projectId}</span>
          <h2>{project.config.projectName}</h2>
        </div>
        <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
          <span className="chip">{project.config.framework}</span>
          <span className="chip">{project.config.language}</span>
          <span className="chip">{project.config.cssStrategy}</span>
          <span className="chip">{project.config.folderStructure}</span>
        </div>
      </div>

      <div className="story-ingestion-card">
        <form onSubmit={handleAddStory}>
          <div className="form-group">
            <label className="form-label">User Story Description *</label>
            <textarea 
              value={userStory} 
              onChange={e => setUserStory(e.target.value)} 
              className="form-textarea" 
              rows="3" 
              required
            />
          </div>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            <input 
              type="file" 
              accept="image/*" 
              onChange={e => setWireframeFile(e.target.files[0])} 
              required
              style={{ padding: '0.5rem' }}
            />
            <button type="submit" className="btn-primary">Generate Story & Extend Project</button>
          </div>
        </form>
      </div>

      <div className="suite-tabs">
        <button className={`tab-btn ${activeTab === 'graph' ? 'active' : ''}`} onClick={() => setActiveTab('graph')}>Dependency Graph</button>
        <button className={`tab-btn ${activeTab === 'files' ? 'active' : ''}`} onClick={() => setActiveTab('files')}>Code Base Files</button>
        <button className={`tab-btn ${activeTab === 'matrix' ? 'active' : ''}`} onClick={() => setActiveTab('matrix')}>Traceability Matrix</button>
      </div>

      {activeTab === 'files' && (
          <ul style={{ listStyle: 'none' }}>
            {(project.filesScanned || []).map(f => (
              <li key={f} className="file-item" style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
                <FileIcon size={16} /> {f}
              </li>
            ))}
          </ul>
      )}

      <div className="workspace-banner" style={{marginBottom: '32px'}}>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start'}}>
          <div>
            <h2>Project History</h2>
            <p className="subtitle" style={{marginTop: '4px'}}>A complete timeline of all actions and AI operations in this project.</p>
          </div>
          <div style={{display: 'flex', gap: '8px'}}>
            <select className="form-select" style={{width: 'auto', height: '36px', padding: '0 12px'}}>
              <option>All Events</option>
            </select>
            <select className="form-select" style={{width: 'auto', height: '36px', padding: '0 12px'}}>
              <option>Sprint 1</option>
            </select>
          </div>
        </div>
      </div>

      <div className="timeline">
        <div className="timeline-item">
          <div className="timeline-time">
            <span>09:15 AM</span>
            <span>Today</span>
          </div>
          <div className="timeline-node success"></div>
          <div className="timeline-content">
            <div className="timeline-header">
              <span className="status-badge analysis" style={{background: 'var(--status-analysis-bg)', color: 'var(--status-analysis-text)'}}>AI_PREPROCESSING</span>
              <span className="status-badge success">COMPLETED</span>
            </div>
            <p style={{marginTop: '12px', fontSize: '14px'}}>Ingestion and preprocessing of document 'RequirementSpec-V2.0.docx' successfully completed.</p>
          </div>
        </div>

        <div className="timeline-item">
          <div className="timeline-time">
            <span>10:00 AM</span>
            <span>Today</span>
          </div>
          <div className="timeline-node running"></div>
          <div className="timeline-content">
            <div className="timeline-header">
              <span className="status-badge analysis" style={{background: 'var(--status-analysis-bg)', color: 'var(--status-analysis-text)'}}>AI_PREPROCESSING</span>
              <span className="status-badge running" style={{background: 'transparent', border: '1px solid var(--status-running-text)'}}>• RUNNING</span>
            </div>
            <p style={{marginTop: '12px', fontSize: '14px'}}>Requirement document ingestion pipeline started.</p>
          </div>
        </div>

        <div className="timeline-item">
          <div className="timeline-time">
            <span>11:30 AM</span>
            <span>Today</span>
          </div>
          <div className="timeline-node success"></div>
          <div className="timeline-content">
            <div className="timeline-header">
              <span className="status-badge analysis">REQUIREMENT_ANALYSIS</span>
              <span className="status-badge success">COMPLETED</span>
            </div>
            <p style={{marginTop: '12px', fontSize: '14px'}}>Automated extraction of functional requirements, system boundaries, and target user personas.</p>
          </div>
        </div>
        
        {/* Actual Dynamic Stories in Timeline format */}
        {(project.storyGraph?.stories || []).map((s, index) => (
          <div className="timeline-item" key={s.id}>
            <div className="timeline-time">
              <span>Dynamic</span>
              <span>Story</span>
            </div>
            <div className="timeline-node success"></div>
            <div className="timeline-content">
              <div className="timeline-header">
                <span className="status-badge success" style={{background: '#E8FAEF', color: '#22C55E'}}>STORY_GENERATION</span>
                <span className="status-badge success">COMPLETED</span>
              </div>
              <p style={{marginTop: '12px', fontSize: '14px'}}>
                <strong>{s.id}:</strong> {s.title} (Component: <code>{s.component}</code>)
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
