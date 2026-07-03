import React from 'react'
import { Checkbox, IconButton, TableCell, TableRow, TextField, useTheme } from '@mui/material'
import CheckBoxIcon from '@mui/icons-material/CheckBox';
import DisabledByDefaultIcon from '@mui/icons-material/DisabledByDefault';

export default function ActionsTableRow({ row, onChange }) {
    const theme = useTheme()
    const border = theme.palette.divider

    return (
        <TableRow hover>
            <TableCell sx={{ fontSize: 13 }}>{row.document}</TableCell>
            <TableCell align="center" sx={{ maxWidth: 50, px: 0 }}>
                <IconButton
                    size="small"
                    onClick={() => onChange({ relevant: !row.relevant })}
                    sx={{ maxWidth: 50 }}
                >
                    {row.relevant
                        ? <CheckBoxIcon fontSize="small" sx={{ color: 'success.main' }} />
                        : <DisabledByDefaultIcon fontSize="small" sx={{ color: 'error.main' }} />}
                </IconButton>
            </TableCell>
            <TableCell align="center" sx={{ maxWidth: 50, px: 0 }}>
                <IconButton
                    size="small"
                    onClick={() => onChange({ privileged: !row.privileged })}
                    sx={{ maxWidth: 50 }}
                >
                    {row.privileged
                        ? <CheckBoxIcon fontSize="small" sx={{ color: 'success.main' }} />
                        : <DisabledByDefaultIcon fontSize="small" sx={{ color: 'error.main' }} />}
                </IconButton>
            </TableCell>
            <TableCell>
                <TextField
                    variant="standard"
                    size="small"
                    fullWidth
                    placeholder="Add reasoning…"
                    value={row.reasoning}
                    onChange={(e) => onChange({ reasoning: e.target.value })}
                    InputProps={{ disableUnderline: true }}
                    sx={{
                        '& .MuiInputBase-root': {
                            px: 1,
                            py: 0.5,
                            borderRadius: 0.5,
                            border: '1px solid transparent',
                            transition: 'border-color 0.15s',
                        },
                        '& .MuiInputBase-root.Mui-focused': {
                            border: `1px solid ${border}`,
                        },
                    }}
                />
            </TableCell>
            <TableCell align="center" sx={{ maxWidth: 50, px: 0 }}>
                <Checkbox
                    size="small"
                    checked={row.actioned}
                    onChange={(e) => onChange({ actioned: e.target.checked })}
                    sx={{ maxWidth: 50 }}
                />
            </TableCell>
        </TableRow>
    )
}
