import { useState } from 'react'

export default function CreateProjectModal({ onClose, onSuccess }) {
  const [formData, setFormData] = useState({
    projectName: '',
    framework: 'React',
    language: 'TypeScript',
    cssStrategy: 'Separate',
    folderStructure: 'Feature-based'
  })

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => {
      const nextData = { ...prev, [name]: value };
      // Enforce TypeScript for Angular
      if (name === 'framework' && value === 'Angular') {
        nextData.language = 'TypeScript';
      }
      return nextData;
    });
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!formData.projectName.trim()) return alert('Project Name is required')

    try {
      const res = await fetch('/api/v1/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      })
      const data = await res.json()
      if (data.config && data.config.projectId) {
        onSuccess(data.config.projectId)
      }
    } catch (err) {
      alert('Failed to create project')
      console.error(err)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h3 style={{fontSize: '24px', fontWeight: 600, color: 'var(--text-heading)', marginBottom: '4px'}}>Configure New Project</h3>
        <p className="subtitle" style={{fontSize: '14px', marginBottom: '24px'}}>Set up your tech stack and scaffolding.</p>
        <form onSubmit={handleSubmit}>
          
          <div className="form-group">
            <label className="form-label">Project Name</label>
            <input name="projectName" value={formData.projectName} onChange={handleChange} className="form-input" required />
          </div>

          <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem' }}>
            <div className="flex-1">
              <label className="form-label">Framework</label>
              <select name="framework" value={formData.framework} onChange={handleChange} className="form-select">
                <option value="React">React</option>
                <option value="Angular">Angular</option>
              </select>
            </div>
            <div className="flex-1">
              <label className="form-label">Language</label>
              <select name="language" value={formData.language} onChange={handleChange} className="form-select">
                <option value="TypeScript">TypeScript</option>
                {formData.framework === 'React' && <option value="JavaScript">JavaScript</option>}
              </select>
            </div>
          </div>

          <div className="form-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary">Initialize Project</button>
          </div>
        </form>
      </div>
    </div>
  )
}
