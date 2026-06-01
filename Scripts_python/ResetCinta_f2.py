from robodk import *
from robolink import *

RDK = Robolink()
# --- CONFIGURACIÓN EXACTA ---
MECHANISM_NAME = 'cinta_fresa2'
FRAME_MOV_NAME = 'MOV_fresa2'

cinta = RDK.Item(MECHANISM_NAME)
padre = RDK.Item(FRAME_MOV_NAME)

# 1. Devolver la cinta a la posición inicial física (0 mm)
if cinta.Valid():
    cinta.setJoints([0])
    print("Mecanismo devuelto a 0.")

# 2. Limpiar el árbol de objetos
if padre.Valid():
    hijos = padre.Childs()
    
    # Esta variable nos ayudará a saber si ya guardamos la plantilla original
    plantilla_conservada = False
    
    # Recorremos al revés para borrar de forma segura
    for item in reversed(hijos):
        if item.Name() == 'brick_fresa': 
            
            # Si es el PRIMER 'brick_naranja' que encuentra viniendo desde atrás
            # (o el único que queda), lo tratamos como la plantilla original.
            if not plantilla_conservada:
                item.setPose(transl(0, 100, 0) * rotz(pi/2))
                plantilla_conservada = True  # Marcamos que ya tenemos nuestra plantilla a salvo
                print("Plantilla original guardada y posicionada.")
                continue  # Salta al siguiente objeto sin borrar este
            
            # Si ya habías conservado uno, los demás 'brick_naranja' son clones viejos.
            # No entran al 'if' anterior y caen aquí abajo para ser eliminados.
            
        # Se elimina cualquier clon viejo o residuo de la simulación anterior
        item.Delete()
        
    print("Cajas viejas eliminadas. Sistema reseteado con un solo brick.")
else:
    print(f"ERROR: No se encontró el Frame '{FRAME_MOV_NAME}'. Revisa el nombre.")
