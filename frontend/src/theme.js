import { createTheme } from '@mui/material/styles'

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#3B4CCA',
      light: '#5A64FF',
      dark: '#253E9F',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#6a1b9a',
      contrastText: '#ffffff',
    },
    text: {
      primary: '#0E1A2B',
      secondary: '#64748B',
    },
    background: {
      default: '#F7F8FB',
      paper: '#ffffff',
    },
    divider: '#E6E9EF',
    brand: {
      accent: '#3B4CCA',
      ink: '#0E1A2B',
      muted: '#64748B',
      soft: '#F7F8FB',
      gold: '#E0A82E',
      highlight: '#EEF1FF',
    },
  },
  shape: {
    borderRadius: 20,
  },
  typography: {
    fontFamily: ['Inter', 'system-ui', 'sans-serif'].join(','),
    h1: {
      fontWeight: 800,
      lineHeight: 1.05,
    },
    h2: {
      fontWeight: 800,
      lineHeight: 1.05,
    },
    h3: {
      fontWeight: 800,
      lineHeight: 1.1,
    },
    button: {
      textTransform: 'none',
      fontWeight: 700,
    },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        html: {
          scrollbarWidth: 'none',
          '&::-webkit-scrollbar': {
            display: 'none',
          },
        },
        body: {
          backgroundColor: '#F7F8FB',
          scrollbarWidth: 'none',
          '&::-webkit-scrollbar': {
            display: 'none',
          },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 20,
          textTransform: 'none',
          fontWeight: 700,
        },
        containedPrimary: {
          backgroundColor: '#3B4CCA',
          color: '#ffffff',
          '&:hover': {
            backgroundColor: '#2E3CA8',
          },
        },
        outlined: {
          borderColor: '#E6E9EF',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 20,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 20,
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          borderRadius: 0,
          backgroundColor: 'rgba(255,255,255,0.92)',
          backdropFilter: 'blur(10px)',
          borderBottom: '1px solid rgba(0,0,0,0.08)',
        },
      },
    },
  },
})

export default theme
