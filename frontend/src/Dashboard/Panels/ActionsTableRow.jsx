import React from 'react'
import { Button, Checkbox, IconButton, TableCell, TableRow, TextField, useTheme } from '@mui/material'
import AddBoxIcon from '@mui/icons-material/AddBox';
import CheckBoxIcon from '@mui/icons-material/CheckBox';
import DisabledByDefaultIcon from '@mui/icons-material/DisabledByDefault';

export default function ActionsTableRow({ row, onChange, onSelectDocument }) {
    const theme = useTheme()
    const border = theme.palette.divider
    // Rel/Priv start locked and gray until the LLM has actually proposed a
    // decision for this doc — nothing to toggle before that.
    const pending = !row.hasDecision

    return (
        <TableRow hover>
            <TableCell sx={{ fontSize: 13, px: 0 }}>
                <Button
                    size="small"
                    variant="text"
                    onClick={() => onSelectDocument?.(row.doc)}
                    sx={{ textTransform: 'none', fontSize: 13, px: 1, py: 0.5, minWidth: 0, width: '100%', justifyContent: 'flex-start' }}
                >
                    {row.document}
                </Button>
            </TableCell>
            <TableCell align="center" sx={{ maxWidth: 50, px: 0 }}>
                <IconButton
                    size="small"
                    disabled={pending}
                    onClick={() => onChange({ toggleField: 'relevant' })}
                    sx={{ maxWidth: 50 }}
                >
                    {pending
                        ? <AddBoxIcon fontSize="small" sx={{ color: 'action.disabled' }} />
                        : row.relevant
                            ? <CheckBoxIcon fontSize="small" sx={{ color: 'success.main' }} />
                            : <DisabledByDefaultIcon fontSize="small" sx={{ color: 'error.main' }} />}
                </IconButton>
            </TableCell>
            <TableCell align="center" sx={{ maxWidth: 50, px: 0 }}>
                <IconButton
                    size="small"
                    disabled={pending}
                    onClick={() => onChange({ toggleField: 'privileged' })}
                    sx={{ maxWidth: 50 }}
                >
                    {pending
                        ? <AddBoxIcon fontSize="small" sx={{ color: 'action.disabled' }} />
                        : row.privileged
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
                    inputProps={{ maxLength: 200 }}
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
            <TableCell align="center" sx={{ maxWidth: 100, px: 0 }}>
                <Checkbox
                    size="small"
                    checked={row.actioned}
                    onChange={(e) => onChange({ actioned: e.target.checked })}
                    sx={{ maxWidth: 100 }}
                />
            </TableCell>
        </TableRow>
    )
}
