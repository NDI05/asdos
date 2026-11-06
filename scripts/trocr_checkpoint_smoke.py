"""Offline synthetic inference and one gradient step; never claims handwriting accuracy."""
import argparse,json,os,time
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-dir',type=Path,default=Path('models/trocr-base-handwritten'))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if a.output.exists():p.error('Output exists')
    a.output.mkdir(parents=True)
    report={'status':'failed','fixture':'synthetic_printed_only','handwriting_accuracy_measured':False,'model_promoted':False}
    started=time.monotonic()
    try:
        import torch
        from PIL import Image,ImageDraw
        from scripts.trocr_runtime import load_model,sha
        processor,model,device=load_model(a.model_dir)
        report.update(device=device,weights_sha256=sha(a.model_dir/'model.safetensors'))
        image=Image.new('RGB',(500,70),'white');ImageDraw.Draw(image).text((15,20),'RAM menyimpan data sementara.',fill='black',font_size=26)
        pixels=processor(images=image,return_tensors='pt').pixel_values.to(device)
        model.eval()
        with torch.inference_mode():
            generated=model.generate(pixels,max_new_tokens=48,num_beams=1,do_sample=False)
        report['synthetic_prediction']=processor.batch_decode(generated,skip_special_tokens=True)[0]
        model.train();opt=torch.optim.SGD(model.parameters(),lr=1e-6)
        target=processor.tokenizer('RAM menyimpan data sementara.',return_tensors='pt').input_ids.to(device)
        loss=model(pixel_values=pixels,labels=target).loss
        loss.backward();opt.step()
        report.update(status='checkpoint_inference_and_backward_succeeded',synthetic_training_loss=loss.item())
    except Exception as exc:
        report.update(error_type=type(exc).__name__,error=str(exc))
    report['seconds']=round(time.monotonic()-started,2)
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));return 0 if report['status'].endswith('succeeded') else 2

if __name__=='__main__':raise SystemExit(main())
