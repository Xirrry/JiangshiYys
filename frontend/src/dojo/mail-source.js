export function mailSource(row){return [622502,622503].includes(row.type)?'xiajian':'dojo'}
export function mailTypeLabel(row){return row.type===622502?'狭间暗域·战斗奖励':row.type===622503?'狭间暗域·阵眼奖励':row.type===400179?'道馆·场次奖励':'道馆奖励'}
export function mailShortLabel(row){return row.type===622502?'狭间·战斗':row.type===622503?'狭间·阵眼':'道馆·场次'}
