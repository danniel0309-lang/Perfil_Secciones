(defun PF:ToString (v)
  (cond
    ((null v) "")
    ((= (type v) 'STR) v)
    ((= (type v) 'INT) (itoa v))
    ((= (type v) 'REAL) (rtos v 2 8))
    ((= (type v) 'VARIANT) (PF:ToString (vlax-variant-value v)))
    (T (vl-princ-to-string v))
  )
)

(defun PF:IsList (x)
  (= (type x) 'LIST)
)

(defun PF:ReplaceAll (str old new / pos)
  (setq str (PF:ToString str))
  (while (setq pos (vl-string-search old str))
    (setq str (vl-string-subst new old str pos))
  )
  str
)

(defun PF:NormalizeClipboardText (str)
  (setq str (PF:ToString str))
  (setq str (PF:ReplaceAll str (chr 9)  " "))
  (setq str (PF:ReplaceAll str (chr 10) " "))
  (setq str (PF:ReplaceAll str (chr 13) " "))
  (setq str (PF:ReplaceAll str ";" " "))
  (while (vl-string-search "  " str)
    (setq str (PF:ReplaceAll str "  " " "))
  )
  (vl-string-trim " " str)
)

(defun PF:SplitBySpace (str / pos tok lst)
  (setq lst '())
  (setq str (vl-string-trim " " (PF:ToString str)))
  (while (> (strlen str) 0)
    (setq pos (vl-string-search " " str))
    (if pos
      (progn
        (setq tok (substr str 1 pos))
        (setq str (vl-string-trim " " (substr str (+ pos 2))))
      )
      (progn
        (setq tok str)
        (setq str "")
      )
    )
    (if (/= tok "")
      (setq lst (append lst (list tok)))
    )
  )
  lst
)

(defun PF:SplitByTab (str / pos tok lst)
  (setq lst '())
  (setq str (PF:ToString str))
  (while (setq pos (vl-string-search (chr 9) str))
    (setq tok (substr str 1 pos))
    (setq lst (append lst (list tok)))
    (setq str (substr str (+ pos 2)))
  )
  (setq lst (append lst (list str)))
  lst
)

(defun PF:SplitLines (str / pos tok lst)
  (setq lst '())
  (setq str (PF:ToString str))
  (setq str (PF:ReplaceAll str (chr 13) ""))
  (while (setq pos (vl-string-search (chr 10) str))
    (setq tok (substr str 1 pos))
    (setq lst (append lst (list tok)))
    (setq str (substr str (+ pos 2)))
  )
  (setq lst (append lst (list str)))
  lst
)

(defun PF:JoinStringsWithSpace (lst / out itm)
  (setq out "")
  (foreach itm lst
    (setq itm (vl-string-trim " " (PF:ToString itm)))
    (if (/= itm "")
      (setq out
        (if (= out "")
          itm
          (strcat out " " itm)
        )
      )
    )
  )
  out
)

(defun PF:TokenToReal (tok / val)
  (setq tok (PF:ToString tok))
  (if (and (not (vl-string-search "." tok))
           (vl-string-search "," tok))
    (setq tok (PF:ReplaceAll tok "," "."))
  )
  (setq val (distof tok 2))
)

(defun PF:ParseClipboardValues (str / toks vals val)
  (setq toks (PF:SplitBySpace (PF:NormalizeClipboardText str)))
  (setq vals '())
  (foreach tok toks
    (setq val (PF:TokenToReal tok))
    (if val
      (setq vals (append vals (list val)))
    )
  )
  vals
)

(defun PF:ParseClipboardStrings (str)
  (PF:SplitBySpace (PF:NormalizeClipboardText str))
)

(defun PF:GetClipboardText (/ html win clip raw txt)
  (setq txt "")
  (setq html (vl-catch-all-apply 'vlax-create-object (list "htmlfile")))
  (if (not (vl-catch-all-error-p html))
    (progn
      (setq win  (vlax-get-property html 'ParentWindow))
      (setq clip (vlax-get-property win 'ClipboardData))
      (setq raw  (vl-catch-all-apply 'vlax-invoke-method (list clip 'GetData "Text")))
      (if (not (vl-catch-all-error-p raw))
        (setq txt (PF:ToString raw))
      )
      (vlax-release-object html)
    )
  )
  txt
)

(defun PF:Pad3 (n / s)
  (setq s (itoa (abs (fix n))))
  (while (< (strlen s) 3)
    (setq s (strcat "0" s))
  )
  s
)

(defun PF:FormatK (dist / sgn d km mts)
  (setq sgn "")
  (if (< dist 0.0)
    (progn
      (setq sgn "-")
      (setq dist (abs dist))
    )
  )
  (setq d (fix (+ dist 0.5)))
  (setq km (fix (/ d 1000)))
  (setq mts (- d (* km 1000)))
  (strcat sgn "K" (itoa km) "+" (PF:Pad3 mts))
)

(defun PF:AllDigitsP (str / i ch ok)
  (setq str (PF:ToString str))
  (setq ok (/= str ""))
  (setq i 1)
  (while (and ok (<= i (strlen str)))
    (setq ch (substr str i 1))
    (if (not (wcmatch ch "#"))
      (setq ok nil)
    )
    (setq i (1+ i))
  )
  ok
)

(defun PF:NormalizeKLabel (s)
  (setq s (strcase (PF:ToString s)))
  (setq s (PF:ReplaceAll s " " ""))
  s
)

(defun PF:ValidKLabel (s / pos km mts)
  (setq s (PF:NormalizeKLabel s))
  (setq pos (vl-string-search "+" s))
  (and
    (> (strlen s) 0)
    (= (substr s 1 1) "K")
    pos
    (> pos 0)
    (setq km (substr s 2 (- pos 1)))
    (setq mts (substr s (+ pos 2)))
    (PF:AllDigitsP km)
    (PF:AllDigitsP mts)
  )
)

(defun PF:ParseKToDist (s / pos km mts)
  (setq s (PF:NormalizeKLabel s))
  (if (PF:ValidKLabel s)
    (progn
      (setq pos (vl-string-search "+" s))
      (setq km  (substr s 2 (- pos 1)))
      (setq mts (substr s (+ pos 2)))
      (+ (* 1000.0 (atoi km)) (atoi mts))
    )
    nil
  )
)

(defun PF:BuildOffsetsFromKLabels (labels / vals firstDist curDist)
  (setq vals '())
  (if (and (PF:IsList labels) labels)
    (progn
      (setq firstDist (PF:ParseKToDist (car labels)))
      (if firstDist
        (foreach s labels
          (setq curDist (PF:ParseKToDist s))
          (if curDist
            (setq vals (append vals (list (- curDist firstDist))))
          )
        )
      )
    )
  )
  vals
)

(defun PF:ParseAdditionalAbscissa (tok absMode firstDist / txt actual val)
  (setq txt (vl-string-trim " " (PF:ToString tok)))
  (cond
    ((= absMode "Excel")
      (cond
        ((PF:ValidKLabel txt)
          (setq actual (PF:ParseKToDist txt))
          (if (and actual firstDist)
            (- actual firstDist)
            nil
          )
        )
        ((setq val (PF:TokenToReal txt))
          (if (and firstDist (>= val 0.0))
            (- val firstDist)
            nil
          )
        )
        (T nil)
      )
    )
    (T
      (setq val (PF:TokenToReal txt))
      (if (and val (>= val 0.0))
        val
        nil
      )
    )
  )
)

(defun PF:LastItem (lst)
  (if (and (PF:IsList lst) (> (length lst) 0))
    (nth (1- (length lst)) lst)
    nil
  )
)

(defun PF:ExtraPointP (p)
  (and
    (PF:IsList p)
    (= (length p) 3)
    (numberp (nth 0 p))
    (= (type (nth 1 p)) 'STR)
    (numberp (nth 2 p))
  )
)

(defun PF:StrictIncreasingP (lst / ok prev itm)
  (setq ok T)
  (if (and (PF:IsList lst) lst)
    (progn
      (setq prev (car lst))
      (foreach itm (cdr lst)
        (if (<= itm prev)
          (setq ok nil)
        )
        (setq prev itm)
      )
    )
    (setq ok nil)
  )
  ok
)

(defun PF:BuildOffsetsAuto (n dx / lst i)
  (setq lst '())
  (setq i 0)
  (repeat n
    (setq lst (append lst (list (* i dx))))
    (setq i (1+ i))
  )
  lst
)

(defun PF:PointP (p)
  (and
    (PF:IsList p)
    (>= (length p) 2)
    (numberp (car p))
    (numberp (cadr p))
  )
)

(defun PF:NumberListP (lst / ok)
  (setq ok (PF:IsList lst))
  (if ok
    (foreach a lst
      (if (not (numberp a))
        (setq ok nil)
      )
    )
  )
  ok
)

(defun PF:SafeNthNum (lst idx def)
  (if (PF:NumberListP lst)
    (if (and (>= idx 0) (< idx (length lst)) (numberp (nth idx lst)))
      (nth idx lst)
      def
    )
    def
  )
)

(defun PF:MaxNumList (lst / m)
  (if (PF:NumberListP lst)
    (progn
      (setq m (car lst))
      (foreach a (cdr lst)
        (if (> a m) (setq m a))
      )
      m
    )
    0.0
  )
)

(defun PF:MinNumList (lst / m)
  (if (PF:NumberListP lst)
    (progn
      (setq m (car lst))
      (foreach a (cdr lst)
        (if (< a m) (setq m a))
      )
      m
    )
    0.0
  )
)

(defun PF:FloorInt (v)
  (if (= v (fix v))
    (fix v)
    (if (> v 0.0)
      (fix v)
      (1- (fix v))
    )
  )
)

(defun PF:Pow10 (e / r)
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

(defun PF:NiceStep (rng / raw exp base frac)
  (if (<= rng 0.0)
    1.0
    (progn
      (setq raw (/ rng 5.0))
      (setq exp (PF:FloorInt (/ (log raw) (log 10.0))))
      (setq base (PF:Pow10 exp))
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

(defun PF:Clamp (v a b)
  (max a (min b v))
)

(defun PF:EnsureDashedLinetype ()
  (if (not (tblsearch "LTYPE" "DASHED"))
    (vl-cmdf "_.-LINETYPE" "_Load" "DASHED" "acad.lin")
  )
)

(defun PF:DrawLine (p1 p2)
  (vl-cmdf "_.LINE" p1 p2 "")
)

(defun PF:DrawRect (p1 p2)
  (vl-cmdf "_.RECTANG" p1 p2)
)

(defun PF:DrawTextMC (pt h rot txt)
  (vl-cmdf "_.TEXT" "_J" "_MC" pt h rot txt)
)

(defun PF:DrawTextMR (pt h rot txt)
  (vl-cmdf "_.TEXT" "_J" "_MR" pt h rot txt)
)

(defun PF:DrawTextML (pt h rot txt)
  (vl-cmdf "_.TEXT" "_J" "_ML" pt h rot txt)
)

(defun PF:DrawTextMCColor (pt h rot txt color / oldColor)
  (setq oldColor (getvar "CECOLOR"))
  (setvar "CECOLOR" color)
  (PF:DrawTextMC pt h rot txt)
  (setvar "CECOLOR" oldColor)
)

(defun PF:DrawTextMLColor (pt h rot txt color / oldColor)
  (setq oldColor (getvar "CECOLOR"))
  (setvar "CECOLOR" color)
  (PF:DrawTextML pt h rot txt)
  (setvar "CECOLOR" oldColor)
)

(defun PF:DrawXColor (pt size color / oldColor x y d)
  (setq oldColor (getvar "CECOLOR"))
  (setvar "CECOLOR" color)
  (setq x (car pt))
  (setq y (cadr pt))
  (setq d (/ size 2.0))
  (PF:DrawLine (list (- x d) (- y d)) (list (+ x d) (+ y d)))
  (PF:DrawLine (list (- x d) (+ y d)) (list (+ x d) (- y d)))
  (setvar "CECOLOR" oldColor)
)

(defun PF:FmtElev (z)
  (rtos z 2 3)
)

(defun PF:BuildProfilePts (vals xGrid0 xOffs xMinOff yGridBase refZ vExag dx / pts i x y z xoff)
  (setq pts '())
  (setq i 0)
  (repeat (length vals)
    (setq z (nth i vals))
    (setq xoff (PF:SafeNthNum xOffs i (* i dx)))
    (setq x (+ xGrid0 (- xoff xMinOff)))
    (setq y (+ yGridBase (* (- z refZ) vExag)))
    (setq pts (append pts (list (list x y))))
    (setq i (1+ i))
  )
  pts
)

(defun PF:DrawPolylineColor (pts color / oldColor pt)
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

(defun PF:GetTrendColor (idx / colors)
  (setq colors '("4" "6" "2" "30" "1" "140"))
  (nth idx colors)
)

(defun c:PERFILTN
  (/ *error* oldCmdEcho oldOsMode oldCEColor oldCELType ok
     dx title base raw vals n absMode rawAbs absVals absTxt xOffs firstDist
     nTrend tmp idx rawT valsT trendVals trendNames defName nameIn
     addMode rawAdd addRows addCols addRow addZ addX addAbsRaw addDesc addMid extraPts
     rowNum extraPt extraLabel
     x0 y0 profW rng zmin zmax stepZ refZ topZ
     txtH dataH titleH leftW rightW rowAbsH rowCotaH rowTitleH
     numCotaRows xGrid0 xPlotRight xFrameRight
     yAbsTop yGridBase yGridTop yTop targetGridH vExag x pts series color
     i z gridY titleX rowBase lab xoff
     xMinData xMaxData)

  (vl-load-com)

  (setq oldCmdEcho (getvar "CMDECHO"))
  (setq oldOsMode  (getvar "OSMODE"))
  (setq oldCEColor (getvar "CECOLOR"))
  (setq oldCELType (getvar "CELTYPE"))

  (defun *error* (msg)
    (setvar "CMDECHO" oldCmdEcho)
    (setvar "OSMODE" oldOsMode)
    (setvar "CECOLOR" oldCEColor)
    (setvar "CELTYPE" oldCELType)
    (if (and msg
             (/= msg "Function cancelled")
             (/= msg "quit / exit abort"))
      (princ (strcat "\nError: " msg))
    )
    (princ)
  )

  (setvar "CMDECHO" 0)
  (setvar "OSMODE" 0)
  (setq ok T)
  (setq trendVals '())
  (setq trendNames '())
  (setq xOffs '())
  (setq absVals '())
  (setq firstDist nil)
  (setq extraPts '())

  (initget "Auto Excel")
  (setq absMode (getkword "\nDesea usar abscisas [Auto/Excel] <Auto>: "))
  (if (null absMode) (setq absMode "Auto"))

  (if (= absMode "Auto")
    (progn
      (setq dx (getreal "\nDistancia entre progresivas (m): "))
      (if (or (null dx) (<= dx 0.0))
        (progn
          (setq ok nil)
          (princ "\nDistancia invalida.")
        )
      )
    )
  )

  (if ok
    (progn
      (prompt "\nCopie en Excel la fila o columna de cotas de la linea principal.")
      (getstring T "\nCuando ya esten copiadas, presione Enter: ")
      (setq raw  (PF:GetClipboardText))
      (setq vals (PF:ParseClipboardValues raw))
      (setq n (length vals))
      (if (< n 2)
        (progn
          (setq ok nil)
          (princ "\nNo se detectaron suficientes cotas en el portapapeles.")
        )
      )
    )
  )

  (if (and ok (= absMode "Excel"))
    (progn
      (prompt "\nCopie en Excel la columna de progresivas en formato K0+5, K0+15, K1+230, una por fila.")
      (getstring T "\nCuando ya esten copiadas, presione Enter: ")
      (setq rawAbs  (PF:GetClipboardText))
      (setq absVals (mapcar 'PF:NormalizeKLabel (PF:ParseClipboardStrings rawAbs)))

      (cond
        ((/= (length absVals) n)
          (setq ok nil)
          (princ "\nLa cantidad de progresivas debe ser igual a la cantidad de cotas.")
        )
        (T
          (setq idx 0)
          (while (and ok (< idx n))
            (setq absTxt (nth idx absVals))
            (if (not (PF:ValidKLabel absTxt))
              (progn
                (setq ok nil)
                (princ
                  (strcat
                    "\nLa progresiva de la fila "
                    (itoa (1+ idx))
                    " no tiene un formato valido. Use K0+5, K0+15, K1+230, etc."
                  )
                )
              )
            )
            (setq idx (1+ idx))
          )

          (if ok
            (progn
              (setq firstDist (PF:ParseKToDist (car absVals)))
              (setq xOffs (PF:BuildOffsetsFromKLabels absVals))
              (if (or (not firstDist)
                      (not (PF:NumberListP xOffs))
                      (/= (length xOffs) n)
                      (not (PF:StrictIncreasingP xOffs)))
                (progn
                  (setq ok nil)
                  (princ "\nNo fue posible construir correctamente las distancias horizontales desde las progresivas de Excel.")
                )
              )
            )
          )
        )
      )
    )
  )

  (if (and ok (= absMode "Auto"))
    (setq xOffs (PF:BuildOffsetsAuto n dx))
  )

  (if ok
    (progn
      (setq nTrend nil)
      (while (null nTrend)
        (setq tmp (getint "\nCuantas lineas de tendencia desea anexar? [0-6] <0>: "))
        (cond
          ((null tmp) (setq nTrend 0))
          ((and (>= tmp 0) (<= tmp 6)) (setq nTrend tmp))
          (T (princ "\nIngrese un numero entre 0 y 6."))
        )
      )

      (setq idx 1)
      (while (and ok (<= idx nTrend))
        (prompt (strcat "\nCopie en Excel la fila o columna de cotas de la linea de tendencia " (itoa idx) "."))
        (getstring T "\nCuando ya esten copiadas, presione Enter: ")
        (setq rawT  (PF:GetClipboardText))
        (setq valsT (PF:ParseClipboardValues rawT))
        (cond
          ((< (length valsT) 2)
            (setq ok nil)
            (princ (strcat "\nNo se detectaron suficientes cotas para la linea de tendencia " (itoa idx) "."))
          )
          ((/= (length valsT) n)
            (setq ok nil)
            (princ (strcat "\nLa linea de tendencia " (itoa idx) " debe tener la misma cantidad de cotas que la linea principal."))
          )
          (T
            (setq trendVals (append trendVals (list valsT)))
            (setq defName (strcat "COTA TN " (itoa (+ idx 1))))
            (setq nameIn (getstring T (strcat "\nNombre para la linea de tendencia " (itoa idx) " <" defName ">: ")))
            (if (= nameIn "") (setq nameIn defName))
            (setq trendNames (append trendNames (list nameIn)))
          )
        )
        (setq idx (1+ idx))
      )
    )
  )

  (if ok
    (progn
      (setq title (getstring T "\nTitulo del perfil: "))
      (setq base  (getpoint "\nPunto base inferior izquierdo del cuadro: "))
      (if (= title "") (setq title "PERFIL TOPOGRAFICO"))
      (if (not (PF:PointP base))
        (progn
          (setq ok nil)
          (princ "\nNo se selecciono un punto valido.")
        )
      )
    )
  )

  (if ok
    (progn
      (initget "Si No")
      (setq addMode (getkword "\nDesea anexar puntos adicionales desde Excel? [Si/No] <No>: "))
      (if (null addMode) (setq addMode "No"))

      (if (= addMode "Si")
        (progn
          (prompt "\nCopie en Excel una o varias filas con el formato: COTA | DESCRIPCION | ABSCISA.")
          (if (= absMode "Excel")
            (prompt "\nLa ABSCISA debe coincidir con el perfil, preferiblemente en formato K0+000, K1+230, etc.")
            (prompt "\nLa ABSCISA debe ser numerica y no negativa, coincidiendo con el abscisado del perfil.")
          )
          (getstring T "\nCuando ya esten copiadas, presione Enter: ")
          (setq rawAdd  (PF:GetClipboardText))
          (setq addRows (PF:SplitLines rawAdd))
          (setq rowNum 0)

          (foreach addRow addRows
            (setq addRow (PF:ToString addRow))
            (if (/= (vl-string-trim " \t" addRow) "")
              (progn
                (setq rowNum (1+ rowNum))
                (setq addCols (PF:SplitByTab addRow))
                (if (< (length addCols) 3)
                  (progn
                    (setq ok nil)
                    (princ
                      (strcat
                        "\nLa fila " (itoa rowNum)
                        " de puntos adicionales no tiene las tres columnas requeridas: COTA, DESCRIPCION y ABSCISA."
                      )
                    )
                  )
                  (progn
                    (setq addZ (PF:TokenToReal (nth 0 addCols)))
                    (setq addAbsRaw (PF:LastItem addCols))
                    (setq addX (PF:ParseAdditionalAbscissa addAbsRaw absMode firstDist))
                    (setq addMid '())
                    (setq idx 1)
                    (while (< idx (1- (length addCols)))
                      (setq addMid (append addMid (list (nth idx addCols))))
                      (setq idx (1+ idx))
                    )
                    (setq addDesc (PF:JoinStringsWithSpace addMid))
                    (if (= addDesc "")
                      (setq addDesc "PUNTO")
                    )

                    (if (or (null addZ) (null addX))
                      (progn
                        (setq ok nil)
                        (if (= absMode "Excel")
                          (princ
                            (strcat
                              "\nLa fila " (itoa rowNum)
                              " de puntos adicionales tiene una cota invalida o una abscisa que no coincide con el formato del perfil."
                            )
                          )
                          (princ
                            (strcat
                              "\nLa fila " (itoa rowNum)
                              " de puntos adicionales tiene una cota invalida o una abscisa negativa/no numerica."
                            )
                          )
                        )
                      )
                      (if (PF:ExtraPointP (list addZ addDesc addX))
                        (setq extraPts (cons (list addZ addDesc addX) extraPts))
                        (progn
                          (setq ok nil)
                          (princ (strcat "\nNo fue posible interpretar correctamente la fila " (itoa rowNum) " de puntos adicionales."))
                        )
                      )
                    )
                  )
                )
              )
            )
          )

          (if ok
            (setq extraPts (reverse extraPts))
          )
          (if (and ok (= rowNum 0))
            (progn
              (setq ok nil)
              (princ "\nNo se detectaron filas validas para los puntos adicionales.")
            )
          )
        )
      )
    )
  )

  (if ok
    (progn
      (PF:EnsureDashedLinetype)
      (setq x0 (car base))
      (setq y0 (cadr base))

      (if (= absMode "Excel")
        (progn
          (if (null firstDist)
            (setq firstDist (PF:ParseKToDist (car absVals)))
          )
          (setq xOffs (PF:BuildOffsetsFromKLabels absVals))
          (setq dx 1.0)
        )
        (if (or (null dx) (<= dx 0.0))
          (setq dx 1.0)
        )
      )

      (if (or (not (PF:NumberListP xOffs))
              (/= (length xOffs) n))
        (progn
          (setq ok nil)
          (princ "\nNo fue posible definir las distancias horizontales del perfil.")
        )
      )

      (if ok
        (progn
          (setq xMinData (PF:MinNumList xOffs))
          (setq xMaxData (PF:MaxNumList xOffs))
          (foreach extraPt extraPts
            (if (PF:ExtraPointP extraPt)
              (progn
                (setq xMinData (min xMinData (nth 2 extraPt)))
                (setq xMaxData (max xMaxData (nth 2 extraPt)))
              )
            )
          )
          (setq profW (- xMaxData xMinData))
        )
      )

      (if (and ok (<= profW 0.0))
        (progn
          (setq ok nil)
          (princ "\nLa longitud horizontal del perfil es invalida.")
        )
      )
    )
  )

  (if ok
    (progn
      (setq zmin (apply 'min vals))
      (setq zmax (apply 'max vals))

      (foreach series trendVals
        (setq zmin (min zmin (apply 'min series)))
        (setq zmax (max zmax (apply 'max series)))
      )

      (foreach extraPt extraPts
        (if (PF:ExtraPointP extraPt)
          (progn
            (setq zmin (min zmin (car extraPt)))
            (setq zmax (max zmax (car extraPt)))
          )
        )
      )

      (setq rng (- zmax zmin))
      (if (< rng 0.001)
        (setq rng 0.001)
      )

      (setq txtH   (PF:Clamp (/ profW 70.0) 0.70 2.20))
      (setq dataH  (* txtH 0.85))
      (setq titleH (* txtH 1.55))

      (setq leftW      (* txtH 9.20))
      (setq rightW     (* txtH 1.70))
      (setq rowAbsH    (* txtH 6.50))
      (setq rowCotaH   (* txtH 6.10))
      (setq rowTitleH  (* txtH 2.40))
      (setq numCotaRows (+ 1 nTrend))

      (setq targetGridH (max (* profW 0.285) (* txtH 18.0)))
      (setq vExag (/ targetGridH rng))

      (setq stepZ (PF:NiceStep rng))
      (setq refZ  (* stepZ (PF:FloorInt (/ zmin stepZ))))
      (setq topZ  refZ)
      (while (< topZ zmax)
        (setq topZ (+ topZ stepZ))
      )

      (setq xGrid0      (+ x0 leftW))
      (setq xPlotRight  (+ xGrid0 profW))
      (setq xFrameRight (+ xPlotRight rightW))

      (setq yAbsTop   (+ y0 rowAbsH))
      (setq yGridBase (+ yAbsTop (* numCotaRows rowCotaH)))
      (setq yGridTop  (+ yGridBase (* (- topZ refZ) vExag)))
      (setq yTop      (+ yGridTop rowTitleH))

      (PF:DrawRect (list x0 y0) (list xFrameRight yTop))

      (PF:DrawLine (list x0 yAbsTop) (list xFrameRight yAbsTop))
      (setq idx 1)
      (while (< idx numCotaRows)
        (PF:DrawLine
          (list x0 (+ yAbsTop (* idx rowCotaH)))
          (list xFrameRight (+ yAbsTop (* idx rowCotaH)))
        )
        (setq idx (1+ idx))
      )

      (setq z refZ)
      (while (<= z topZ)
        (setq gridY (+ yGridBase (* (- z refZ) vExag)))
        (setvar "CECOLOR" "1")
        (setvar "CELTYPE" "DASHED")
        (PF:DrawLine (list xGrid0 gridY) (list xPlotRight gridY))
        (setq z (+ z stepZ))
      )

      (setq i 0)
      (repeat n
        (setq xoff (PF:SafeNthNum xOffs i (* i dx)))
        (setq x (+ xGrid0 (- xoff xMinData)))
        (setvar "CECOLOR" "1")
        (setvar "CELTYPE" "DASHED")
        (PF:DrawLine (list x yGridBase) (list x yGridTop))
        (setq i (1+ i))
      )

      (setvar "CECOLOR" oldCEColor)
      (setvar "CELTYPE" oldCELType)

      (PF:DrawLine (list xPlotRight yGridBase) (list xPlotRight yGridTop))

      (setq pts (PF:BuildProfilePts vals xGrid0 xOffs xMinData yGridBase refZ vExag dx))
      (PF:DrawPolylineColor pts "3")

      (setq idx 0)
      (foreach series trendVals
        (setq color (PF:GetTrendColor idx))
        (setq pts (PF:BuildProfilePts series xGrid0 xOffs xMinData yGridBase refZ vExag dx))
        (PF:DrawPolylineColor pts color)
        (setq idx (1+ idx))
      )

      (foreach extraPt extraPts
        (if (PF:ExtraPointP extraPt)
          (progn
            (setq x (+ xGrid0 (- (nth 2 extraPt) xMinData)))
            (setq z (car extraPt))
            (setq gridY (+ yGridBase (* (- z refZ) vExag)))
            (PF:DrawXColor (list x gridY) (* txtH 1.10) "6")
            (setq extraLabel (strcat (nth 1 extraPt) " " (PF:FmtElev z)))
            (PF:DrawTextMLColor
              (list (+ x (* txtH 0.80)) (+ gridY (* txtH 0.45)))
              dataH
              0
              extraLabel
              "6"
            )
          )
        )
      )

      (setq z refZ)
      (while (<= z topZ)
        (setq gridY (+ yGridBase (* (- z refZ) vExag)))
        (PF:DrawTextMR (list (- xGrid0 (* txtH 0.60)) gridY) dataH 0 (PF:FmtElev z))
        (setq z (+ z stepZ))
      )

      (setq i 0)
      (repeat n
        (setq xoff (PF:SafeNthNum xOffs i (* i dx)))
        (setq x (+ xGrid0 (- xoff xMinData)))
        (setq absTxt
          (if (= absMode "Excel")
            (nth i absVals)
            (PF:FormatK xoff)
          )
        )
        (PF:DrawTextMCColor
          (list x (+ y0 (/ rowAbsH 2.0)))
          dataH
          90
          absTxt
          "5"
        )
        (setq i (1+ i))
      )

      (setq i 0)
      (repeat n
        (setq xoff (PF:SafeNthNum xOffs i (* i dx)))
        (setq x (+ xGrid0 (- xoff xMinData)))
        (PF:DrawTextMCColor
          (list x (+ yAbsTop (/ rowCotaH 2.0)))
          dataH
          90
          (PF:FmtElev (nth i vals))
          "7"
        )
        (setq i (1+ i))
      )

      (setq idx 0)
      (foreach series trendVals
        (setq color (PF:GetTrendColor idx))
        (setq rowBase (+ yAbsTop (* (1+ idx) rowCotaH)))
        (setq i 0)
        (repeat n
          (setq xoff (PF:SafeNthNum xOffs i (* i dx)))
          (setq x (+ xGrid0 (- xoff xMinData)))
          (PF:DrawTextMCColor
            (list x (+ rowBase (/ rowCotaH 2.0)))
            dataH
            90
            (PF:FmtElev (nth i series))
            color
          )
          (setq i (1+ i))
        )
        (setq idx (1+ idx))
      )

      (PF:DrawTextMC
        (list (+ x0 (/ leftW 2.0)) (+ y0 (/ rowAbsH 2.0)))
        dataH
        0
        "ABSCISAS"
      )

      (PF:DrawTextMC
        (list (+ x0 (/ leftW 2.0)) (+ yAbsTop (/ rowCotaH 2.0)))
        dataH
        0
        "COTA TN"
      )

      (setq idx 0)
      (while (< idx nTrend)
        (setq rowBase (+ yAbsTop (* (1+ idx) rowCotaH)))
        (setq lab (nth idx trendNames))
        (PF:DrawTextMC
          (list (+ x0 (/ leftW 2.0)) (+ rowBase (/ rowCotaH 2.0)))
          dataH
          0
          lab
        )
        (setq idx (1+ idx))
      )

      (setq titleX (+ x0 (/ (- xFrameRight x0) 2.0)))
      (PF:DrawTextMC
        (list titleX (+ yGridTop (/ rowTitleH 2.0)))
        titleH
        0
        title
      )

      (princ
        (strcat
          "\nPerfil generado con linea principal, "
          (itoa nTrend)
          " lineas de tendencia y "
          (itoa (length extraPts))
          " puntos adicionales."
        )
      )
    )
  )

  (setvar "CMDECHO" oldCmdEcho)
  (setvar "OSMODE" oldOsMode)
  (setvar "CECOLOR" oldCEColor)
  (setvar "CELTYPE" oldCELType)
  (princ)
)

(defun c:PERFIL ()
  (c:PERFILTN)
)