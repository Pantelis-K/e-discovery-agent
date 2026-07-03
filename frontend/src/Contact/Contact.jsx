import React from 'react'
import { Container, Typography } from '@mui/material'

export default function Contact() {
    return (
        <Container maxWidth="sm" sx={{ py: 6 }}>
            <Typography variant="h5" gutterBottom>Contact Us</Typography>
            <Typography color="text.secondary">Email: demo@example.com</Typography>
            <Typography color="text.secondary">Phone: +44 20 0000 0000</Typography>
        </Container>
    )
}
