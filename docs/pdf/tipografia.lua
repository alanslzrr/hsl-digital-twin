function Code(el)
  local text = el.text
  local replacements = {['…']='...', ['–']='-', ['−']='-', ['×']='*', ['⁹']='^9', ['≤']='<=', ['≥']='>='}
  for k,v in pairs(replacements) do text = text:gsub(k,v) end
  return pandoc.RawInline('latex', '\\nolinkurl{' .. text .. '}')
end
