import { useEffect, useState } from 'react'
import {
  Box,
  Button,
  Card,
  CardContent,
  Container,
  Stack,
  Typography,
} from '@mui/material'

function App() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/health/')
      .then((res) => res.json())
      .then((data) => setHealth(data))
      .catch(() => setHealth({ status: 'unreachable' }))
  }, [])

  return (
    <Container maxWidth="md" sx={{ py: 6 }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h4" fontWeight={700}>
            E-Discovery Review Agent
          </Typography>
          <Typography color="text.secondary">
            A React + MUI frontend paired with a Django backend skeleton.
          </Typography>
        </Box>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Backend status
            </Typography>
            <Typography variant="body1">
              {health ? `Status: ${health.status}` : 'Checking backend...'}
            </Typography>
            {health && health.service && (
              <Typography color="text.secondary" sx={{ mt: 1 }}>
                Service: {health.service}
              </Typography>
            )}
          </CardContent>
        </Card>

        <Stack direction="row" spacing={2}>
          <Button variant="contained" href="https://mui.com" target="_blank">
            MUI docs
          </Button>
          <Button variant="outlined" href="https://docs.djangoproject.com" target="_blank">
            Django docs
          </Button>
        </Stack>
      </Stack>
    </Container>
  )
}

export default App
