#!/usr/bin/env python3
"""Video de telemetría medida en Gazebo (no se presenta como captura GUI)."""
import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv')
    parser.add_argument('--output', required=True)
    parser.add_argument('--scenario', required=True)
    args=parser.parse_args()
    data=np.genfromtxt(args.csv, delimiter=',', names=True)
    fig=plt.figure(figsize=(10,6))
    ax=fig.add_subplot(111,projection='3d')
    ax.set(xlim=(-1,21),ylim=(-7,7),zlim=(0,14),xlabel='x [m]',ylabel='y [m]',zlabel='z [m]')
    ax.view_init(elev=23,azim=-55)
    slope=np.tan(np.pi/12)
    xx,yy=np.meshgrid(np.linspace(0,20,10),np.linspace(-7,7,10))
    ax.plot_surface(xx,yy,xx*slope,color='#82a66a',alpha=.25)
    trace,=ax.plot([],[],[],color='#ef6c00',lw=2)
    point,=ax.plot([],[],[],'o',color='#ef6c00',markersize=9)
    ref,=ax.plot([],[],[],'x',color='black',markersize=7)
    # Platform attitude triad: measured roll/pitch/yaw.
    axes=[ax.plot([],[],[],color=c,lw=3)[0] for c in ['r','g','b']]
    title=fig.suptitle('')
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    writer=FFMpegWriter(fps=20,bitrate=1400)
    indices=np.linspace(0,len(data)-1,480).astype(int)
    with writer.saving(fig,args.output,100):
        for i in indices:
            d=data[i]
            pos=np.array([d['x'],d['y'],d['z']])
            trace.set_data(data['x'][:i+1:5],data['y'][:i+1:5]);trace.set_3d_properties(data['z'][:i+1:5])
            point.set_data([pos[0]],[pos[1]]);point.set_3d_properties([pos[2]])
            ref.set_data([d['target_x']],[d['target_y']]);ref.set_3d_properties([d['target_z']])
            r,p,y=d['roll'],d['pitch'],d['yaw']
            cr,sr,cp,sp,cy,sy=np.cos(r),np.sin(r),np.cos(p),np.sin(p),np.cos(y),np.sin(y)
            R=np.array([[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],[sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]])
            for j,line in enumerate(axes):
                end=pos+R[:,j]*1.2
                line.set_data([pos[0],end[0]],[pos[1],end[1]]);line.set_3d_properties([pos[2],end[2]])
            title.set_text(f'{args.scenario} · reproducción de telemetría de Gazebo · t={d["time"]:.1f} s\nError {d["position_error"]:.3f} m · orientación {np.rad2deg(d["orientation_error"]):.2f}°')
            writer.grab_frame()
    plt.close(fig)


if __name__=='__main__':
    main()
