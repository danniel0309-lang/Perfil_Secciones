(defun SC:ToString (v)
  (cond
    ((null v) "")
    ((= (type v) 'STR) v)
    ((= (type v) 'INT) (itoa v))
    ((= (type v) 'REAL) (rtos v 2 8))
    ((= (type v) 'VARIANT) (SC:ToString (vlax-variant-value v)))
    (T (vl-princ-to-string v))
  )
)

(defun SC:IsList (x)
  (= (type x) 'LIST)
)

(defun SC:ReplaceAll (str old new / pos)
  (setq str (SC:ToString str))
  (while (setq pos (vl-string-search old str))
    (setq str (vl-string-subst new old str pos))
  )
  str
)

(defun SC:Trim (s)
  (vl-string-trim " \t\r\n" (SC:ToString s))
)

(defun SC:TokenToReal (tok / val)
  (setq tok (SC:Trim tok))
  (if (and (/= tok "")
           (not (vl-string-search "." tok))
           (vl-string-search "," tok))
    (setq tok (SC:ReplaceAll tok "," "."))
  )
  (setq val (distof tok 2))
)

(defun SC:GetClipboardText (/ html win clip raw txt)
  (setq txt "")
  (setq html (vl-catch-all-apply 'vlax-create-object (list "htmlfile")))
  (if (not (vl-catch-all-error-p html))
    (progn
      (setq win  (vlax-get-property html 'ParentWindow))
      (setq clip (vlax-get-property win 'ClipboardData))
      (setq raw  (vl-catch-all-apply 'vlax-invoke-method (list clip 'GetData "Text")))
      (if (not (vl-catch-all-error-p raw))
        (setq txt (SC:ToString raw))
      )
      (vlax-release-object html)
    )
  )
  txt
)

(defun SC:SplitLines (txt / out cur i ch)
  (setq txt (SC:ReplaceAll (SC:ToString txt) (strcat (chr 13) (chr 10)) (chr 10)))
  (setq txt (SC:ReplaceAll txt (chr 13) (chr 10)))
  (setq out '())
  (setq cur "")
  (setq i 1)
  (while (<= i (strlen txt))
    (setq ch (substr txt i 1))
    (if (= ch (chr 10))
      (progn
        (if (/= (SC:Trim cur) "")
          (setq out (append out (list cur)))
        )
        (setq cur "")
      )
      (setq cur (strcat cur ch))
    )
    (setq i (1+ i))
  )
  (if (/= (SC:Trim cur) "")
    (setq out (append out (list cur)))
  )
  out
)

(defun SC:SplitTabLine (str / i ch cur out)
  (setq out '())
  (setq cur "")
  (setq i 1)
  (while (<= i (strlen str))
    (setq ch (substr str i 1))
    (cond
      ((= ch (chr 9))
        (setq out (append out (list cur)))
        (setq cur "")
      )
      ((or (= ch (chr 13)) (= ch (chr 10))))
      (T
        (setq cur (strcat cur ch))
      )
    )
    (setq i (1+ i))
  )
  (setq out (append out (list cur)))
  out
)

(defun SC:NumberListP (lst / ok)
  (setq ok (SC:IsList lst))
  (if ok
    (foreach a lst
      (if (not (numberp a))
        (setq ok nil)
      )
    )
  )
  ok
)

(defun SC:PointP (p)
  (and
    (SC:IsList p)
    (>= (length p) 2)
    (numberp (car p))
    (numberp (cadr p))
  )
)

(defun SC:SafeNthNum (lst idx def)
  (if (SC:NumberListP lst)
    (if (and (>= idx 0) (< idx (length lst)) (numberp (nth idx lst)))
      (nth idx lst)
      def
    )
    def
  )
)

(defun SC:Clamp (v a b)
  (max a (min b v))
)

(defun SC:FloorInt (v)
  (if (= v (fix v))
    (fix v)
    (if (> v 0.0)
      (fix v)
      (1- (fix v))
    )
  )
)

(defun SC:Pow10 (e / r)
  (setq r 1.0)
  (if (>= e 0)
    (repeat e
      (setq r (* r 10.0))
    )
    (repeat (- e)
      (setq r (/ r 10.0))
    )
  )
  r
)

(defun SC:NiceStep (rng / raw exp base frac)
  (if (<= rng 0.0)
    1.0
    (progn
      (setq raw (/ rng 5.0))
      (setq exp (SC:FloorInt (/ (log raw) (log 10.0))))
      (setq base (SC:Pow10 exp))
      (setq frac (/ raw base))
      (cond
        ((<= frac 1.0) (* 1.0 base))
        ((<= frac 2.0) (* 2.0 base))
        ((<= frac 5.0) (* 5.0 base))
        (T             (* 10.0 base))
      )
    )
  )
)

(defun SC:ListIndex (val lst / i ans)
  (setq i 0)
  (setq ans nil)
  (while (and (< i (length lst)) (null ans))
    (if (= val (nth i lst))
      (setq ans i)
    )
    (setq i (1+ i))
  )
  ans
)

(defun SC:EnsureDashedLinetype ()
  (if (not (tblsearch "LTYPE" "DASHED"))
    (vl-cmdf "_.-LINETYPE" "_Load" "DASHED" "acad.lin")
  )
)

(defun SC:DrawLine (p1 p2)
  (vl-cmdf "_.LINE" p1 p2 "")
)

(defun SC:DrawTextMC (pt h rot txt)
  (vl-cmdf "_.TEXT" "_J" "_MC" pt h rot txt)
)

(defun SC:DrawTextMR (pt h rot txt)
  (vl-cmdf "_.TEXT" "_J" "_MR" pt h rot txt)
)

(defun SC:DrawTextML (pt h rot txt)
  (vl-cmdf "_.TEXT" "_J" "_ML" pt h rot txt)
)

(defun SC:DrawTextMCColor (pt h rot txt color / oldColor)
  (setq oldColor (getvar "CECOLOR"))
  (setvar "CECOLOR" color)
  (SC:DrawTextMC pt h rot txt)
  (setvar "CECOLOR" oldColor)
)

(defun SC:FmtElev (z)
  (rtos z 2 3)
)

(defun SC:FmtDist (x)
  (rtos x 2 1)
)

(defun SC:LabelByCol (idx)
  (cond
    ((= idx 0) "PAR")
    ((= idx 1) "SAR")
    ((= idx 2) "BV")
    ((= idx 3) "EJE")
    ((= idx 4) "BV")
    ((= idx 5) "SAR")
    ((= idx 6) "PAR")
    (T (strcat "P" (itoa (1+ idx))))
  )
)

(defun SC:DefaultLabelsByCount (n)
  (cond
    ((= n 2) '("BV" "BV"))
    ((= n 3) '("BV" "EJE" "BV"))
    ((= n 4) '("SAR" "BV" "BV" "SAR"))
    ((= n 5) '("SAR" "BV" "EJE" "BV" "SAR"))
    ((= n 6) '("PAR" "SAR" "BV" "BV" "SAR" "PAR"))
    ((= n 7) '("PAR" "SAR" "BV" "EJE" "BV" "SAR" "PAR"))
    ((= n 8) '("PAR" "SAR" "BV" "EJE" "BV" "SAR" "PAR" "P8"))
    (T '())
  )
)

(defun SC:ExtractSectionFromRow (cells / absc vals labs cols i cell val)
  (setq cells (mapcar 'SC:Trim cells))
  (setq absc (if cells (car cells) ""))
  (setq vals '())
  (setq labs '())
  (setq cols '())
  (setq i 0)
  (foreach cell (cdr cells)
    (setq val (SC:TokenToReal cell))
    (if val
      (progn
        (setq vals (append vals (list val)))
        (setq labs (append labs (list (SC:LabelByCol i))))
        (setq cols (append cols (list i)))
      )
    )
    (setq i (1+ i))
  )
  (if (and (>= (length vals) 2) (<= (length vals) 8))
    (list absc vals labs cols)
    nil
  )
)

(defun SC:GetSectionsFromClipboard (raw / lines secs cells sec)
  (setq secs '())
  (foreach ln (SC:SplitLines raw)
    (setq cells (SC:SplitTabLine ln))
    (setq sec  (SC:ExtractSectionFromRow cells))
    (if sec
      (setq secs (append secs (list sec)))
    )
  )
  secs
)

(defun SC:IndexOfString (str lst / i ans)
  (setq ans nil)
  (setq i 0)
  (while (and (< i (length lst)) (null ans))
    (if (= (strcase (SC:ToString (nth i lst))) (strcase (SC:ToString str)))
      (setq ans i)
    )
    (setq i (1+ i))
  )
  ans
)

(defun SC:BuildCumOffsets (dxVals / out acc)
  (setq out (list 0.0))
  (setq acc 0.0)
  (foreach d dxVals
    (setq acc (+ acc d))
    (setq out (append out (list acc)))
  )
  out
)

(defun SC:ShiftList (lst shift / out)
  (setq out '())
  (foreach a lst
    (setq out (append out (list (- a shift))))
  )
  out
)

(defun SC:AutoXValsFromCols (cols sep / out c)
  (setq out '())
  (foreach c cols
    (setq out (append out (list (* (- c 3) sep))))
  )
  out
)

(defun SC:ManualXVals (dxVals descs cols / cum idxE zeroAt idxCol3)
  (setq cum (SC:BuildCumOffsets dxVals))
  (setq idxE (SC:IndexOfString "EJE" descs))
  (cond
    (idxE
      (setq zeroAt (SC:SafeNthNum cum idxE 0.0))
      (SC:ShiftList cum zeroAt)
    )
    ((and cols (> (length cols) 0))
      (setq zeroAt nil)
      (setq idxCol3 (SC:ListIndex 3 cols))
      (if idxCol3
        (setq zeroAt (SC:SafeNthNum cum idxCol3 0.0))
      )
      (if zeroAt
        (SC:ShiftList cum zeroAt)
        cum
      )
    )
    (T
      cum
    )
  )
)

(defun SC:PointPromptName (idx descs / idxE lbl)
  (setq lbl  (SC:ToString (nth idx descs)))
  (setq idxE (SC:IndexOfString "EJE" descs))
  (cond
    ((= (strcase lbl) "EJE") "EJE")
    ((and idxE (< idx idxE)) (strcat lbl " IZQ"))
    ((and idxE (> idx idxE)) (strcat lbl " DER"))
    (T lbl)
  )
)

(defun SC:ReadManualDx (descs absc / out i d nm1 nm2 fail)
  (setq out '())
  (setq i 0)
  (setq fail nil)
  (prompt (strcat "\nIngrese las distancias para la seccion " absc ":"))
  (while (and (< i (1- (length descs))) (not fail))
    (setq nm1 (SC:PointPromptName i descs))
    (setq nm2 (SC:PointPromptName (1+ i) descs))
    (setq d (getreal (strcat "\nDistancia entre " nm1 " y " nm2 ": ")))
    (if (or (null d) (<= d 0.0))
      (setq fail T)
      (setq out (append out (list d)))
    )
    (setq i (1+ i))
  )
  (if fail nil out)
)

(defun SC:GetXValsForSection (sec modoX sepX / absc descs cols dxVals)
  (setq absc  (SC:ToString (nth 0 sec)))
  (setq descs (nth 2 sec))
  (setq cols  (nth 3 sec))
  (if (= modoX "Automaticas")
    (SC:AutoXValsFromCols cols sepX)
    (progn
      (setq dxVals (SC:ReadManualDx descs absc))
      (if dxVals
        (SC:ManualXVals dxVals descs cols)
        nil
      )
    )
  )
)

(defun SC:ExtractNumericValuesFromCells (cells / vals val)
  (setq vals '())
  (foreach cell cells
    (setq val (SC:TokenToReal cell))
    (if val
      (setq vals (append vals (list val)))
    )
  )
  vals
)

(defun SC:GetTrendLinesForSection (sec / ans out more raw lines vals expected ok)
  (setq out '())
  (setq expected (length (nth 1 sec)))
  (setq more T)

  (while (and more (< (length out) 4))
    (if (= (length out) 0)
      (progn
        (initget "Si No")
        (setq ans (getkword (strcat "\nDesea anexar linea de tendencia a la seccion " (SC:ToString (nth 0 sec)) " [Si/No] <No>: ")))
      )
      (progn
        (initget "Si No")
        (setq ans (getkword "\nDesea anexar otra linea de tendencia [Si/No] <No>: "))
      )
    )

    (if (null ans) (setq ans "No"))

    (if (= ans "Si")
      (progn
        (setq ok nil)
        (while (not ok)
          (prompt
            (strcat
              "\nCopie desde Excel UNA fila de la linea de tendencia."
              "\nPuede copiar la fila completa de la tabla o solo las cotas."
              "\nLa fila debe contener "
              (itoa expected)
              " cotas."
            )
          )
          (getstring T "\nCuando ya este copiada, presione Enter: ")
          (setq raw   (SC:GetClipboardText))
          (setq lines (SC:SplitLines raw))
          (if (> (length lines) 0)
            (progn
              (setq vals (SC:ExtractNumericValuesFromCells (SC:SplitTabLine (car lines))))
              (if (= (length vals) expected)
                (progn
                  (setq out (append out (list vals)))
                  (setq ok T)
                )
                (princ (strcat "\nLa linea de tendencia debe tener exactamente " (itoa expected) " cotas. Intente otra vez."))
              )
            )
            (princ "\nNo se detectaron datos validos. Intente otra vez.")
          )
        )
      )
      (setq more nil)
    )
  )
  out
)

(defun SC:ExtractAnnexPointsFromRow (cells / pts i z desc xv)
  (setq pts '())
  (setq cells (mapcar 'SC:Trim cells))
  (setq i 0)
  (while (< (+ i 2) (length cells))
    (setq z    (SC:TokenToReal (nth i cells)))
    (setq desc (SC:ToString (nth (1+ i) cells)))
    (setq xv   (SC:TokenToReal (nth (+ i 2) cells)))
    (if (and z xv)
      (setq pts (append pts (list (list z desc xv))))
    )
    (setq i (+ i 3))
  )
  pts
)

(defun SC:GetAnnexPointsForSection (absc / ans raw lines line pts oneRowPts)
  (initget "Si No")
  (setq ans (getkword (strcat "\nAnexar puntos a la seccion " absc " [Si/No] <No>: ")))
  (if (null ans) (setq ans "No"))
  (if (= ans "Si")
    (progn
      (prompt
        (strcat
          "\nCopie desde Excel UNA o VARIAS filas para los puntos de la seccion "
          absc
          " en grupos de 3 columnas:"
          "\nCota | Descripcion | X   (puede ser X positiva o negativa)"
          "\nTambien puede copiar una sola fila con varios grupos consecutivos."
        )
      )
      (getstring T "\nCuando ya este copiada, presione Enter: ")
      (setq raw (SC:GetClipboardText))
      (setq lines (SC:SplitLines raw))
      (setq pts '())
      (foreach line lines
        (setq oneRowPts (SC:ExtractAnnexPointsFromRow (SC:SplitTabLine line)))
        (if oneRowPts
          (setq pts (append pts oneRowPts))
        )
      )
      (if (= (length pts) 0)
        nil
        pts
      )
    )
    nil
  )
)

(defun SC:BuildSectionPts (vals xVals xGrid0 xMin yGridBase refZ vExag / pts i x y z xv)
  (setq pts '())
  (setq i 0)
  (repeat (length vals)
    (setq z  (nth i vals))
    (setq xv (SC:SafeNthNum xVals i 0.0))
    (setq x  (+ xGrid0 (- xv xMin)))
    (setq y  (+ yGridBase (* (- z refZ) vExag)))
    (setq pts (append pts (list (list x y))))
    (setq i (1+ i))
  )
  pts
)

(defun SC:CollectAllZValues (mainVals trendLists annPts / out one p)
  (setq out '())
  (foreach one mainVals
    (setq out (append out (list one)))
  )
  (foreach one trendLists
    (foreach p one
      (setq out (append out (list p)))
    )
  )
  (foreach p annPts
    (setq out (append out (list (nth 0 p))))
  )
  out
)

(defun SC:DrawPolylineColor (pts color / oldColor pt)
  (if pts
    (progn
      (setq oldColor (getvar "CECOLOR"))
      (setvar "CECOLOR" color)
      (vl-cmdf "_.PLINE")
      (foreach pt pts
        (vl-cmdf pt)
      )
      (vl-cmdf "")
      (setvar "CECOLOR" oldColor)
    )
  )
)

(defun SC:DrawXMarker (pt size / p1 p2 p3 p4)
  (setq p1 (list (- (car pt) (/ size 2.0)) (- (cadr pt) (/ size 2.0))))
  (setq p2 (list (+ (car pt) (/ size 2.0)) (+ (cadr pt) (/ size 2.0))))
  (setq p3 (list (- (car pt) (/ size 2.0)) (+ (cadr pt) (/ size 2.0))))
  (setq p4 (list (+ (car pt) (/ size 2.0)) (- (cadr pt) (/ size 2.0))))
  (SC:DrawLine p1 p2)
  (SC:DrawLine p3 p4)
)

(defun SC:DrawAnnexPoints (annPts xGrid0 xMin yGridBase refZ vExag txtH / p z desc xv x y mk txtPt1 txtPt2 txtH2 oldColor)
  (setq mk    (* txtH 0.75))
  (setq txtH2 (* txtH 0.65))
  (setq oldColor (getvar "CECOLOR"))
  (setvar "CECOLOR" "6")
  (foreach p annPts
    (setq z    (nth 0 p))
    (setq desc (SC:ToString (nth 1 p)))
    (setq xv   (nth 2 p))
    (setq x (+ xGrid0 (- xv xMin)))
    (setq y (+ yGridBase (* (- z refZ) vExag)))

    (SC:DrawXMarker (list x y) mk)

    (setq txtPt1 (list (+ x (* mk 0.90)) (+ y (* mk 0.55))))
    (setq txtPt2 (list (+ x (* mk 0.90)) (- y (* mk 0.95))))

    (if (/= (SC:Trim desc) "")
      (SC:DrawTextML txtPt1 txtH2 0 desc)
    )

    (SC:DrawTextML txtPt2 txtH2 0 (SC:FmtElev z))
  )
  (setvar "CECOLOR" oldColor)
)

(defun SC:DrawTrendLines (trendLists xVals xGrid0 xMin yGridBase refZ vExag / cols idx vals pts col)
  (setq cols '("2" "4" "6" "1"))
  (setq idx 0)
  (foreach vals trendLists
    (setq pts (SC:BuildSectionPts vals xVals xGrid0 xMin yGridBase refZ vExag))
    (setq col (nth idx cols))
    (if (null col) (setq col "2"))
    (SC:DrawPolylineColor pts col)
    (setq idx (1+ idx))
  )
)

(defun SC:DrawOneSection (sec xVals base trendLists annPts / absc vals descs title
                               allZ
                               x0 y0 secW rng zmin zmax stepZ refZ topZ
                               xMin xMax xZeroPaper
                               txtH dataH titleH leftW rightW rowDistH rowDescH rowCotaH rowTitleH
                               xGrid0 xPlotRight xFrameRight yDistTop yDescTop yGridBase yGridTop yTop
                               targetGridH vExag pts i x z xv gridY)

  (setq absc  (SC:ToString (nth 0 sec)))
  (setq vals  (nth 1 sec))
  (setq descs (nth 2 sec))
  (setq title absc)

  (if (= (SC:Trim absc) "")
    (setq title "SIN ABSCISA")
  )

  (setq x0 (car base))
  (setq y0 (cadr base))

  (setq xMin (apply 'min xVals))
  (setq xMax (apply 'max xVals))
  (setq secW (- xMax xMin))
  (if (< secW 0.001)
    (setq secW 0.001)
  )

  (setq allZ (SC:CollectAllZValues vals trendLists annPts))
  (setq zmin (apply 'min allZ))
  (setq zmax (apply 'max allZ))
  (setq rng (- zmax zmin))
  (if (< rng 0.001)
    (setq rng 0.001)
  )

  (setq txtH   (SC:Clamp (/ secW 60.0) 0.70 2.20))
  (setq dataH  (* txtH 0.85))
  (setq titleH (* txtH 1.50))

  (setq leftW     (* txtH 9.20))
  (setq rightW    (* txtH 9.20))
  (setq rowDistH  (* txtH 4.385714))
  (setq rowDescH  (* txtH 5.571429))
  (setq rowCotaH  (* txtH 6.10))
  (setq rowTitleH (* txtH 2.40))

  (setq targetGridH (max (* secW 0.350) (* txtH 18.0)))
  (setq vExag (/ targetGridH rng))

  (setq stepZ (SC:NiceStep rng))
  (setq refZ  (* stepZ (SC:FloorInt (/ zmin stepZ))))
  (setq topZ  refZ)
  (while (< topZ zmax)
    (setq topZ (+ topZ stepZ))
  )

  (setq xGrid0      (+ x0 leftW))
  (setq xPlotRight  (+ xGrid0 secW))
  (setq xFrameRight (+ xPlotRight rightW))

  (setq yDistTop  (+ y0 rowDistH))
  (setq yDescTop  (+ yDistTop rowDescH))
  (setq yGridBase (+ yDescTop rowCotaH))
  (setq yGridTop  (+ yGridBase (* (- topZ refZ) vExag)))
  (setq yTop      (+ yGridTop rowTitleH))

  (SC:DrawLine (list x0 y0) (list xFrameRight y0))
  (SC:DrawLine (list x0 y0) (list x0 yTop))
  (SC:DrawLine (list xFrameRight y0) (list xFrameRight yTop))
  (SC:DrawLine (list x0 yTop) (list xFrameRight yTop))

  (SC:DrawLine (list x0 yDistTop) (list xFrameRight yDistTop))
  (SC:DrawLine (list x0 yDescTop) (list xFrameRight yDescTop))

  (setq z refZ)
  (while (<= z topZ)
    (setq gridY (+ yGridBase (* (- z refZ) vExag)))
    (setvar "CECOLOR" "1")
    (setvar "CELTYPE" "DASHED")
    (SC:DrawLine (list xGrid0 gridY) (list xPlotRight gridY))
    (setq z (+ z stepZ))
  )

  (setq i 0)
  (repeat (length xVals)
    (setq xv (SC:SafeNthNum xVals i 0.0))
    (setq x (+ xGrid0 (- xv xMin)))
    (setvar "CECOLOR" "1")
    (setvar "CELTYPE" "DASHED")
    (SC:DrawLine (list x yGridBase) (list x yGridTop))
    (setq i (1+ i))
  )

  (if (and (<= xMin 0.0) (>= xMax 0.0))
    (progn
      (setq xZeroPaper (+ xGrid0 (- 0.0 xMin)))
      (setvar "CECOLOR" "2")
      (setvar "CELTYPE" "DASHED")
      (SC:DrawLine (list xZeroPaper yGridBase) (list xZeroPaper yGridTop))
    )
  )

  (setvar "CECOLOR" "BYLAYER")
  (setvar "CELTYPE" "BYLAYER")

  (SC:DrawLine (list xPlotRight yGridBase) (list xPlotRight yGridTop))

  (if trendLists
    (SC:DrawTrendLines trendLists xVals xGrid0 xMin yGridBase refZ vExag)
  )

  (setq pts (SC:BuildSectionPts vals xVals xGrid0 xMin yGridBase refZ vExag))
  (SC:DrawPolylineColor pts "3")

  (if annPts
    (SC:DrawAnnexPoints annPts xGrid0 xMin yGridBase refZ vExag txtH)
  )

  (setq z refZ)
  (while (<= z topZ)
    (setq gridY (+ yGridBase (* (- z refZ) vExag)))
    (SC:DrawTextMR (list (- xGrid0 (* txtH 0.60)) gridY) dataH 0 (SC:FmtElev z))
    (SC:DrawTextML (list (+ xPlotRight (* txtH 0.60)) gridY) dataH 0 (SC:FmtElev z))
    (setq z (+ z stepZ))
  )

  (SC:DrawTextMC
    (list (+ x0 (/ leftW 2.0)) (+ y0 (/ rowDistH 2.0)))
    dataH
    0
    "DISTANCIA"
  )

  (SC:DrawTextMC
    (list (+ x0 (/ leftW 2.0)) (+ yDistTop (/ rowDescH 2.0)))
    dataH
    0
    "DESCRIPCION"
  )

  (SC:DrawTextMC
    (list (+ x0 (/ leftW 2.0)) (+ yDescTop (/ rowCotaH 2.0)))
    dataH
    0
    "COTA TN"
  )

  (setq i 0)
  (repeat (length xVals)
    (setq xv (SC:SafeNthNum xVals i 0.0))
    (setq x (+ xGrid0 (- xv xMin)))

    (SC:DrawTextMCColor
      (list x (+ y0 (/ rowDistH 2.0)))
      dataH
      90
      (SC:FmtDist xv)
      "7"
    )

    (SC:DrawTextMCColor
      (list x (+ yDistTop (/ rowDescH 2.0)))
      dataH
      90
      (nth i descs)
      "5"
    )

    (SC:DrawTextMCColor
      (list x (+ yDescTop (/ rowCotaH 2.0)))
      dataH
      90
      (SC:FmtElev (nth i vals))
      "7"
    )

    (setq i (1+ i))
  )

  (SC:DrawTextMC
    (list (+ x0 (/ (- xFrameRight x0) 2.0)) (+ yGridTop (/ rowTitleH 2.0)))
    titleH
    0
    title
  )

  (list (- xFrameRight x0) (- yTop y0))
)

(defun c:SECCIONTN
  (/ *error* oldCmdEcho oldOsMode oldCEColor oldCELType oldCELWeight
     modoSec modoX sepX raw secs secList base hGap vGap xVals
     curX curY startX startY rowMaxH colCount dims sec
     trendLists usarPuntos annPts absc)

  (vl-load-com)

  (setq oldCmdEcho   (getvar "CMDECHO"))
  (setq oldOsMode    (getvar "OSMODE"))
  (setq oldCEColor   (getvar "CECOLOR"))
  (setq oldCELType   (getvar "CELTYPE"))
  (setq oldCELWeight (getvar "CELWEIGHT"))

  (defun *error* (msg)
    (setvar "CMDECHO" oldCmdEcho)
    (setvar "OSMODE" oldOsMode)
    (setvar "CECOLOR" oldCEColor)
    (setvar "CELTYPE" oldCELType)
    (setvar "CELWEIGHT" oldCELWeight)
    (if (and msg
             (/= msg "Function cancelled")
             (/= msg "quit / exit abort"))
      (princ (strcat "\nError: " msg))
    )
    (princ)
  )

  (setvar "CMDECHO" 0)
  (setvar "OSMODE" 0)

  (initget "Una Varias")
  (setq modoSec (getkword "\nDesea hacer [Una/Varias] secciones <Una>: "))
  (if (null modoSec) (setq modoSec "Una"))

  (if (= modoSec "Una")
    (prompt "\nCopie en Excel una sola fila completa de la seccion: ABSCISA + cotas, de izquierda a derecha.")
    (prompt "\nCopie en Excel varias filas completas de la tabla: ABSCISA + cotas, una seccion por cada fila.")
  )
  (getstring T "\nCuando ya este copiado, presione Enter: ")
  (setq raw (SC:GetClipboardText))
  (setq secs (SC:GetSectionsFromClipboard raw))

  (if (= modoSec "Una")
    (if (> (length secs) 0)
      (setq secList (list (car secs)))
      (setq secList nil)
    )
    (setq secList secs)
  )

  (if (or (null secList) (= (length secList) 0))
    (progn
      (princ "\nNo se detectaron filas validas con una abscisa y entre 2 y 8 cotas.")
      (*error* nil)
    )
    (progn
      (initget "Automaticas Manuales")
      (setq modoX (getkword "\nDistancias horizontales en eje X [Automaticas/Manuales] <Automaticas>: "))
      (if (null modoX) (setq modoX "Automaticas"))

      (if (= modoX "Automaticas")
        (progn
          (setq sepX (getreal "\nDistancia horizontal uniforme entre puntos <2.0>: "))
          (if (null sepX) (setq sepX 2.0))
          (if (<= sepX 0.0)
            (setq sepX 2.0)
          )
        )
        (setq sepX nil)
      )

      (setq base (getpoint "\nPunto base inferior izquierdo de la primera seccion: "))
      (if (not (SC:PointP base))
        (progn
          (princ "\nNo se selecciono un punto valido.")
          (*error* nil)
        )
        (progn
          (if (> (length secList) 1)
            (progn
              (setq hGap (getreal "\nSeparacion horizontal entre secciones <5.0>: "))
              (if (null hGap) (setq hGap 5.0))
              (if (< hGap 0.0) (setq hGap 5.0))

              (setq vGap (getreal "\nSeparacion vertical entre filas <5.0>: "))
              (if (null vGap) (setq vGap 5.0))
              (if (< vGap 0.0) (setq vGap 5.0))
            )
            (progn
              (setq hGap 0.0)
              (setq vGap 0.0)
            )
          )

          (initget "Si No")
          (setq usarPuntos (getkword "\nDesea anexar puntos [Si/No] <No>: "))
          (if (null usarPuntos) (setq usarPuntos "No"))

          (SC:EnsureDashedLinetype)

          (setq startX (car base))
          (setq startY (cadr base))
          (setq curX startX)
          (setq curY startY)
          (setq rowMaxH 0.0)
          (setq colCount 0)

          (foreach sec secList
            (setq xVals (SC:GetXValsForSection sec modoX sepX))
            (setq trendLists nil)
            (setq annPts nil)

            (if xVals
              (progn
                (setq trendLists (SC:GetTrendLinesForSection sec))

                (if (= usarPuntos "Si")
                  (progn
                    (setq absc (SC:ToString (nth 0 sec)))
                    (setq annPts (SC:GetAnnexPointsForSection absc))
                  )
                )
              )
            )

            (if (null xVals)
              (princ (strcat "\nNo se pudo generar la seccion " (SC:ToString (nth 0 sec)) "."))
              (progn
                (setq dims (SC:DrawOneSection sec xVals (list curX curY) trendLists annPts))
                (if dims
                  (progn
                    (setq rowMaxH (max rowMaxH (cadr dims)))
                    (setq colCount (1+ colCount))

                    (if (= colCount 5)
                      (progn
                        (setq curX startX)
                        (setq curY (- curY rowMaxH vGap))
                        (setq rowMaxH 0.0)
                        (setq colCount 0)
                      )
                      (setq curX (+ curX (car dims) hGap))
                    )
                  )
                )
              )
            )
          )

          (princ "\nSecciones generadas.")
        )
      )
    )
  )

  (setvar "CMDECHO" oldCmdEcho)
  (setvar "OSMODE" oldOsMode)
  (setvar "CECOLOR" oldCEColor)
  (setvar "CELTYPE" oldCELType)
  (setvar "CELWEIGHT" oldCELWeight)
  (princ)
)

(defun c:SECCION ()
  (c:SECCIONTN)
)