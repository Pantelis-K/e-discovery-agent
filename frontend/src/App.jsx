import { useState } from 'react'
import { Box } from '@mui/material'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import NavBar from './components/NavBar'
import Landing from './Landing/Landing'
import Contact from './Contact/Contact'
import Login from './Login/Login'
import Dashboard from './Dashboard/Dashboard'

function App() {
	const [loggedIn, setLoggedIn] = useState(true) // Set to false for flow in demo

	const demoCases = [
		{ id: 1, name: 'Harrow & Blackwood v. Meridian Foods', type: 'Contract Dispute', status: 'Active · 1,204 documents', emoji: '📝' },
		{ id: 2, name: 'In re: Kessler Data Breach', type: 'Cybersecurity Incident', status: 'Active · 3,850 documents', emoji: '🔐' },
		{ id: 3, name: 'Pennington Vance Patent Litigation', type: 'Patent Infringement', status: 'Active · 962 documents', emoji: '💡' },
		{ id: 4, name: 'Aldridge & Crowe Employment Claim', type: 'Employment Discrimination', status: 'Under Review · 410 documents', emoji: '👔' },
		{ id: 5, name: 'Marchetti Legal M&A Due Diligence', type: 'Mergers & Acquisitions', status: 'Active · 5,120 documents', emoji: '🤝' },
		{ id: 6, name: 'Riverside Holdings Environmental Compliance', type: 'Environmental Regulatory', status: 'Active · 780 documents', emoji: '🌱' },
		{ id: 7, name: 'Stratton Foods Product Liability', type: 'Product Liability', status: 'Active · 2,340 documents', emoji: '⚠️' },
		{ id: 8, name: 'Okonkwo Estate Trade Secret Dispute', type: 'Trade Secret Theft', status: 'Active · 1,675 documents', emoji: '🔒' },
	]

	const handleLogin = () => setLoggedIn(true)

	const handleLogout = () => setLoggedIn(false)

	return (
		<BrowserRouter>
			<Box>
				<NavBar loggedIn={loggedIn} onLogout={handleLogout} />
				<Routes>
					<Route path="/" element={<Landing />} />
					<Route path="/contact" element={<Contact />} />
					<Route path="/login" element={<Login onLogin={handleLogin} />} />
					<Route path="/dashboard" element={loggedIn ? <Dashboard cases={demoCases} /> : <Navigate to="/login" replace />} />
					<Route path="*" element={<Navigate to="/" replace />} />
				</Routes>
			</Box>
		</BrowserRouter>
	)
}

export default App
