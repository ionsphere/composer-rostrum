-- Strict JSON codec with explicit arrays and null, including Unicode escapes.
local J = {null={}}
local array_mt = {}
function J.array(t) return setmetatable(t or {}, array_mt) end
local escapes = {['"']='\\"', ['\\']='\\\\', ['\b']='\\b', ['\f']='\\f', ['\n']='\\n', ['\r']='\\r', ['\t']='\\t'}
local function quote(s)
  return '"' .. s:gsub('[%z\1-\31\\"]', function(c) return escapes[c] or string.format('\\u%04x', c:byte()) end) .. '"'
end
function J.encode(v)
  if v == J.null then return 'null' end
  local t = type(v)
  if t == 'boolean' then return tostring(v) end
  if t == 'number' then assert(v == v and math.abs(v) ~= math.huge, 'non-finite JSON number'); return string.format('%.17g', v) end
  if t == 'string' then return quote(v) end
  assert(t == 'table', 'unsupported JSON value: '..t)
  local out = {}
  if getmetatable(v) == array_mt then
    for i=1,#v do out[i] = J.encode(v[i]) end
    return '['..table.concat(out, ',')..']'
  end
  local keys = {}; for k in pairs(v) do assert(type(k)=='string', 'object key must be a string'); keys[#keys+1]=k end
  table.sort(keys)
  for _,k in ipairs(keys) do out[#out+1] = quote(k)..':'..J.encode(v[k]) end
  return '{'..table.concat(out, ',')..'}'
end
function J.decode(s)
  local p, depth = 1, 0
  local parse
  local function ws() local _,e=s:find('^[ \t\r\n]*',p); p=(e or p-1)+1 end
  local function str()
    assert(s:sub(p,p)=='"', 'expected string'); p=p+1
    local out={}
    while p<=#s do
      local c=s:sub(p,p); p=p+1
      if c=='"' then return table.concat(out) end
      if c=='\\' then
        c=s:sub(p,p); p=p+1
        local map={['"']='"', ['\\']='\\', ['/']='/', b='\b', f='\f', n='\n', r='\r', t='\t'}
        if c=='u' then
          local h=s:sub(p,p+3); assert(h:match('^%x%x%x%x$'), 'bad unicode escape'); p=p+4
          local code=tonumber(h,16)
          if code>=0xD800 and code<=0xDBFF then
            assert(s:sub(p,p+1)=='\\u', 'missing low surrogate'); p=p+2
            h=s:sub(p,p+3); assert(h:match('^%x%x%x%x$'), 'bad low surrogate'); p=p+4
            local low=tonumber(h,16); assert(low>=0xDC00 and low<=0xDFFF, 'bad low surrogate')
            code=0x10000+(code-0xD800)*1024+low-0xDC00
          else assert(code<0xDC00 or code>0xDFFF, 'unpaired surrogate') end
          out[#out+1]=utf8.char(code)
        else assert(map[c], 'bad escape'); out[#out+1]=map[c] end
      else assert(c:byte()>=32, 'control in string'); out[#out+1]=c end
    end
    error('unterminated string')
  end
  parse=function()
    ws(); depth=depth+1; assert(depth<128,'JSON nesting limit')
    local c=s:sub(p,p); local v
    if c=='"' then v=str()
    elseif c=='{' or c=='[' then
      local arr=c=='['; v=arr and J.array() or {}; local close=arr and ']' or '}'
      p=p+1; ws()
      if s:sub(p,p)~=close then
        while true do
          ws()
          if arr then v[#v+1]=parse()
          else local key=str(); ws(); assert(s:sub(p,p)==':','expected colon'); p=p+1
            assert(v[key]==nil,'duplicate object key'); v[key]=parse() end
          ws(); c=s:sub(p,p)
          if c==close then break end
          assert(c==',','expected comma'); p=p+1
        end
      end
      p=p+1
    elseif s:sub(p,p+3)=='true' then v=true; p=p+4
    elseif s:sub(p,p+4)=='false' then v=false; p=p+5
    elseif s:sub(p,p+3)=='null' then v=J.null; p=p+4
    else
      local token=s:match('^%-?%d+%.?%d*[eE]?[+%-]?%d*',p)
      assert(token and not token:match('^%-?0%d') and not token:match('%.$') and not token:match('%.%D'), 'bad JSON number')
      v=tonumber(token); assert(v and v==v and math.abs(v)~=math.huge,'bad JSON number'); p=p+#token
    end
    depth=depth-1; return v
  end
  local result=parse(); ws(); assert(p>#s,'trailing JSON input'); return result
end
return J
